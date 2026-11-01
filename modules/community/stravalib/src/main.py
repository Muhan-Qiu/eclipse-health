"""Strava Sync：stdio JSON-RPC 2.0 模块（每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``activities.normalize`` /
``activities.weekly`` / ``strava.fetch`` / ``deactivate``。

- 不复制上游源码；``strava.fetch`` 懒导入模块 venv 里的 ``stravalib``；
- 网络失败、token 缺失、依赖缺失都返回可读的 JSON-RPC error；
- 不记录活动内容与 token；日志只允许写 stderr，且这里不写。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import DISCLAIMER, normalize_activities, weekly_summary

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.stravalib.stravalib")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
MAX_ACTIVITIES = 2000


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, error: RpcError) -> None:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data:
        payload["error"]["data"] = error.data
    _write(payload)


def health_payload() -> dict[str, Any]:
    available = True
    try:
        import stravalib  # noqa: F401
    except ImportError:
        available = False
    return {"ok": True, "dependencyAvailable": available, "disclaimer": DISCLAIMER}


def _dependency_missing() -> RpcError:
    return RpcError(
        -32005,
        "stravalib 未安装；请在该模块的独立 venv 中安装后再同步",
        {"code": "DEPENDENCY_MISSING"},
    )


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    token = params.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        raise RpcError(-32602, "params.accessToken 缺失", {"code": "INVALID_INPUT"})
    limit = params.get("limit", 30)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ACTIVITIES:
        raise RpcError(-32602, "params.limit 必须是 1..2000 的整数", {"code": "INVALID_INPUT"})
    try:
        from stravalib.client import Client
    except ImportError as exc:
        raise _dependency_missing() from exc
    client = Client(access_token=token.strip())
    try:
        rows: list[Any] = []
        for activity in client.get_activities(limit=limit):
            rows.append(
                {
                    "id": activity.id,
                    "name": activity.name,
                    "sport_type": activity.sport_type or activity.type,
                    "start_date": activity.start_date.isoformat()
                    if activity.start_date
                    else None,
                    "distance": activity.distance,
                    "moving_time": activity.moving_time,
                    "average_heartrate": activity.average_heartrate,
                    "max_heartrate": activity.max_heartrate,
                }
            )
    except Exception as exc:
        raise RpcError(
            -32006,
            f"Strava 请求失败：{type(exc).__name__}",
            {"code": "UPSTREAM_ERROR"},
        ) from exc
    return normalize_activities(rows)


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "Strava Sync",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "activities.normalize",
                "activities.weekly",
                "strava.fetch",
                "deactivate",
            ],
            "health": health_payload(),
            "disclaimer": DISCLAIMER,
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "activities.normalize":
        try:
            return normalize_activities(params.get("activities"))
        except (TypeError, ValueError) as exc:
            raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    if method == "activities.weekly":
        try:
            return weekly_summary(params.get("activities"))
        except (TypeError, ValueError) as exc:
            raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    if method == "strava.fetch":
        return _fetch(params)
    if method in {"activate", "deactivate"}:
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        result = handle(str(method), params)
        _result(request_id, result)
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _error(None, RpcError(-32700, "parse error"))
            continue
        if not isinstance(message, dict) or "method" not in message:
            continue
        if "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

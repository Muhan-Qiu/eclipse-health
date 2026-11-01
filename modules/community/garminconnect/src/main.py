"""Garmin Connect 适配模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：initialize / warmup / health / import.garmin / import.summary / deactivate。

上游 ``garminconnect`` 装在模块独立 venv（B 类），需要 ``network`` 权限。
非官方 API；凭据只传给上游，不写日志、不落盘。错误统一映射为 JSON-RPC error。
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.cyberjunky.garminconnect")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
PERMISSIONS = [item for item in os.environ.get("ECLIPSE_PERMISSIONS", "").split(",") if item]
DISCLAIMER = "非医疗器械，不用于诊断。"

_last_summary: dict[str, Any] = {"activities": 0, "distanceKm": 0.0, "durationMinutes": 0.0}
_last_activities: list[dict[str, Any]] = []


def _load_adapter() -> Any:
    name = "eh_adapter_" + MODULE_ID.replace(".", "_").replace("-", "_")
    path = Path(__file__).resolve().with_name("adapter.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter.py unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


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


def _require_network() -> None:
    # 直接本地运行（测试/自检）时 PERMISSIONS 为空，不额外拦截；核心启动时会注入。
    if PERMISSIONS and "network" not in PERMISSIONS:
        raise RpcError(-32005, "缺少 network 权限", {"code": "PERMISSION_DENIED"})


def _require_upstream() -> Any:
    if importlib.util.find_spec("garminconnect") is None:
        raise RpcError(-32000, "未安装 garminconnect；模块依赖未就绪", {"code": "upstream_unavailable"})
    import garminconnect

    return garminconnect


def _import(params: dict[str, Any]) -> dict[str, Any]:
    try:
        credentials = adapter.build_login(params)
    except adapter.GarminAdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    _require_network()
    garminconnect = _require_upstream()
    count = params.get("count", 10)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 50:
        raise RpcError(-32602, "params.count 必须是 1..50 的整数", {"code": "INVALID_INPUT"})
    client = garminconnect.Garmin(credentials["email"], credentials["password"])
    try:
        client.login()
    except Exception as exc:
        raise RpcError(-32000, f"Garmin 登录失败：{type(exc).__name__}", {"code": "upstream_failed"}) from exc

    try:
        raw_activities = client.get_activities(0, count)
    except Exception as exc:
        raise RpcError(-32000, f"Garmin 活动拉取失败：{type(exc).__name__}", {"code": "upstream_failed"}) from exc
    activities: list[dict[str, Any]] = []
    for raw in raw_activities if isinstance(raw_activities, list) else []:
        try:
            activities.append(adapter.normalize_activity(raw))
        except adapter.GarminAdapterError:
            continue

    today = _dt.date.today().isoformat()
    sleep: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    for fetcher, normalizer, target in (
        ("get_sleep_data", adapter.normalize_sleep, "sleep"),
        ("get_body_composition", adapter.normalize_body, "body"),
    ):
        method = getattr(client, fetcher, None)
        if not callable(method):
            continue
        try:
            normalized = normalizer(method(today))
        except Exception:  # noqa: BLE001, S112 - 单项失败不影响其它数据
            continue
        if target == "sleep":
            sleep = normalized
        else:
            body = normalized

    summary = adapter.summarize(activities)
    _last_summary.update(summary)
    _last_activities[:] = activities
    return {
        "summary": summary,
        "activities": activities,
        "sleep": sleep,
        "body": body,
        "disclaimer": DISCLAIMER,
    }


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "upstreamAvailable": importlib.util.find_spec("garminconnect") is not None,
        "networkPermission": "network" in PERMISSIONS,
        "disclaimer": DISCLAIMER,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, "unsupported apiVersion", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "Garmin Connect 导入",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "import.garmin",
                "import.summary",
                "deactivate",
            ],
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "import.garmin":
        return _import(params)
    if method == "import.summary":
        return {**_last_summary, "activities": _last_activities[:20], "disclaimer": DISCLAIMER}
    if method in {"activate"}:
        return {"ok": True}
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        _result(request_id, handle(str(method), params))
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
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

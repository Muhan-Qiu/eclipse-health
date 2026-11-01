"""Fitbit data-source 模块：stdio JSON-RPC 2.0，每行一条 JSON。

方法与 ``README.md`` 一致；上游 ``fitbit`` 只在 ``fetch``/``auth.exchange`` 中懒加载，
因此 ``health``、``import`` 与纯解析在未安装依赖时仍可用。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (
    DISCLAIMER,
    AdapterError,
    build_auth_url,
    items_for,
    parse_date_range,
    records_from_export,
    summarize_records,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.orcasgit.fitbit")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "fitbit"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "auth.url",
    "auth.exchange",
    "fetch",
    "import",
    "stats",
    "activity.list",
    "sleep.list",
    "body.list",
    "deactivate",
]


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _configure_streams() -> None:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


def _dependency_available() -> bool:
    try:
        return importlib.util.find_spec(DEPENDENCY) is not None
    except (ImportError, ValueError):
        return False


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "dependency": {"name": DEPENDENCY, "available": _dependency_available()},
        "note": DISCLAIMER,
    }


def _require_dependency() -> None:
    if not _dependency_available():
        raise RpcError(
            -32000,
            f"缺少依赖 {DEPENDENCY}；请让核心为模块 venv 安装 dependencies",
            {"code": "MODULE_DEPENDENCY_MISSING"},
        )


def _require_text(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RpcError(-32602, f"params.{key} 缺失", {"code": "INVALID_INPUT"})
    return value.strip()


def _dates(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days: list[str] = []
    while current <= last:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _auth_url(params: dict[str, Any]) -> dict[str, Any]:
    try:
        url = build_auth_url(
            params.get("clientId"), params.get("redirectUri"), params.get("state", "")
        )
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"url": url, "note": DISCLAIMER}


def _auth_exchange(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    import requests

    client_id = _require_text(params, "clientId")
    client_secret = _require_text(params, "clientSecret")
    code = _require_text(params, "code")
    redirect_uri = _require_text(params, "redirectUri")
    response = requests.post(
        "https://api.fitbit.com/oauth2/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        auth=(client_id, client_secret),
        timeout=30,
    )
    if response.status_code != 200:
        raise RpcError(
            -32000,
            f"Fitbit token 交换失败（HTTP {response.status_code}）",
            {"code": "UPSTREAM_ERROR"},
        )
    data = response.json()
    return {
        "accessToken": data.get("access_token"),
        "refreshToken": data.get("refresh_token"),
        "expiresIn": data.get("expires_in"),
        "userId": data.get("user_id"),
        "note": DISCLAIMER,
    }


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    import fitbit

    kind = params.get("kind")
    if kind not in {"activity", "sleep", "body", "heartRate"}:
        raise RpcError(-32602, "params.kind 必须是 activity/sleep/body/heartRate",
                       {"code": "INVALID_INPUT"})
    client_id = _require_text(params, "clientId")
    client_secret = _require_text(params, "clientSecret")
    access_token = _require_text(params, "accessToken")
    refresh_token = params.get("refreshToken")
    client = fitbit.Fitbit(
        client_id,
        client_secret,
        access_token=access_token,
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
    )
    try:
        if kind == "body":
            day = params.get("date")
            if not isinstance(day, str):
                raise RpcError(-32602, "params.date 缺失", {"code": "INVALID_INPUT"})
            payload: dict[str, Any] = client.get_bodyweight(base_date=day)
        else:
            try:
                start, end = parse_date_range(params)
            except AdapterError as exc:
                raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
            payload = {"activities": [], "sleep": [], "dataset": []}
            for day in _dates(start, end):
                if kind == "activity":
                    payload["activities"].append(client.activities(date=day))
                elif kind == "sleep":
                    chunk = client.sleep(date=day)
                    payload["sleep"].extend(chunk.get("sleep", []) if isinstance(chunk, dict) else [])
                else:
                    chunk = client.intraday_time_series(
                        "activities/heart", base_date=day, detail_level="1min"
                    )
                    container = chunk.get("activities-heart-intraday", {}) if isinstance(chunk, dict) else {}
                    payload["dataset"].extend(container.get("dataset", []))
    except RpcError:
        raise
    except Exception as exc:  # 上游异常统一转成可读错误
        raise RpcError(
            -32000,
            f"Fitbit 拉取失败：{type(exc).__name__}",
            {"code": "UPSTREAM_ERROR"},
        ) from exc
    try:
        records = records_from_export(payload, kind, params.get("requestId"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    kind = params.get("kind")
    if not isinstance(kind, str):
        raise RpcError(-32602, "params.kind 缺失", {"code": "INVALID_INPUT"})
    payload = params.get("payload")
    if not isinstance(payload, dict):
        raise RpcError(-32602, "params.payload 必须是对象", {"code": "INVALID_INPUT"})
    try:
        records = records_from_export(payload, kind, params.get("requestId"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def _list(params: dict[str, Any], record_type: str) -> dict[str, Any]:
    try:
        return items_for(params.get("records", []), record_type)
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Fitbit Data Sync",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": CAPABILITIES,
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "auth.url":
        return _auth_url(params)
    if method == "auth.exchange":
        return _auth_exchange(params)
    if method == "fetch":
        return _fetch(params)
    if method == "import":
        return _import(params)
    if method == "stats":
        try:
            return summarize_records(params.get("records", []))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method == "activity.list":
        return _list(params, "activity.session")
    if method == "sleep.list":
        return _list(params, "sleep.session")
    if method == "body.list":
        return _list(params, "body.measurement")
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
        _result(request_id, handle(str(method), params))
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}",
                                    {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    _configure_streams()
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

"""Withings data-source 模块：stdio JSON-RPC 2.0，每行一条 JSON。

``requests`` 只在 ``auth.exchange`` / ``fetch`` 中懒加载；纯解析与导入离线可用。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (
    DISCLAIMER,
    MEASURE_URL,
    TOKEN_URL,
    AdapterError,
    build_auth_url,
    items_for,
    parse_date_argument,
    parse_token_response,
    records_from_export,
    summarize_records,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.vangorra.withings")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "requests"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "auth.url",
    "auth.exchange",
    "fetch",
    "import",
    "stats",
    "measurements.list",
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


def _auth_url(params: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "url": build_auth_url(
                params.get("clientId"), params.get("redirectUri"), params.get("state", "")
            ),
            "note": DISCLAIMER,
        }
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc


def _auth_exchange(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    import requests

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "action": "requesttoken",
                "grant_type": "authorization_code",
                "client_id": _require_text(params, "clientId"),
                "client_secret": _require_text(params, "clientSecret"),
                "code": _require_text(params, "code"),
                "redirect_uri": _require_text(params, "redirectUri"),
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RpcError(-32000, f"Withings token 请求失败：{type(exc).__name__}",
                       {"code": "UPSTREAM_ERROR"}) from exc
    if response.status_code != 200:
        raise RpcError(-32000, f"Withings token 请求失败（HTTP {response.status_code}）",
                       {"code": "UPSTREAM_ERROR"})
    try:
        return parse_token_response(response.json())
    except AdapterError as exc:
        raise RpcError(-32000, exc.message, {"code": exc.code}) from exc


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    import requests

    access_token = _require_text(params, "accessToken")
    try:
        start = parse_date_argument(params.get("startDate", params.get("date")), "startDate")
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    query: dict[str, Any] = {"action": "getmeas", "meastype": 1, "category": 1}
    if "date" not in params and isinstance(params.get("endDate"), str):
        try:
            query["enddate"] = int(
                datetime.fromisoformat(parse_date_argument(params["endDate"], "endDate")).timestamp()
            )
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    query["startdate"] = int(datetime.fromisoformat(start).timestamp())
    try:
        response = requests.get(
            MEASURE_URL,
            params=query,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RpcError(-32000, f"Withings 拉取失败：{type(exc).__name__}",
                       {"code": "UPSTREAM_ERROR"}) from exc
    if response.status_code != 200:
        raise RpcError(-32000, f"Withings 拉取失败（HTTP {response.status_code}）",
                       {"code": "UPSTREAM_ERROR"})
    try:
        records = records_from_export(response.json())
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    payload = params.get("payload")
    if not isinstance(payload, dict):
        raise RpcError(-32602, "params.payload 必须是对象", {"code": "INVALID_INPUT"})
    try:
        records = records_from_export(payload)
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Withings Body Measurements",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": CAPABILITIES,
            "health": health_payload(),
        }
    if method in {"warmup", "health"}:
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
    if method == "measurements.list":
        try:
            return items_for(params.get("records", []))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
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

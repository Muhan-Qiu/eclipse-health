"""Dexcom CGM 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``readings`` / ``latestReading`` /
``deactivate``。凭据只用于当前调用，不落盘、不写日志；pydexcom 在调用时才导入。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.gagebenne.pydexcom")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
_REGIONS = {"us", "eu"}
_LAST_READING: dict[str, Any] | None = None


def _load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location(
        f"{MODULE_ID}.adapter", Path(__file__).with_name("adapter.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("adapter.py 缺失")
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


def _credentials(params: dict[str, Any]) -> tuple[str, str, str]:
    username = params.get("username")
    password = params.get("password")
    if not isinstance(username, str) or not 1 <= len(username) <= 200:
        raise RpcError(-32602, "params.username 缺失或过长", {"code": "INVALID_INPUT"})
    if not isinstance(password, str) or not 1 <= len(password) <= 200:
        raise RpcError(-32602, "params.password 缺失或过长", {"code": "INVALID_INPUT"})
    region = params.get("region", "us")
    if region not in _REGIONS:
        raise RpcError(-32602, "params.region 必须是 us 或 eu", {"code": "INVALID_INPUT"})
    return username, password, str(region)


def _reading_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    data: dict[str, Any] = {}
    for key in ("value", "mmol_l", "trend", "trend_direction"):
        if hasattr(item, key):
            data[key] = getattr(item, key)
    moment = getattr(item, "datetime", None)
    if moment is not None:
        data["timestamp"] = moment.isoformat() if hasattr(moment, "isoformat") else str(moment)
    display = getattr(item, "display_time", None)
    if isinstance(display, str) and display:
        data.setdefault("displayTime", display)
    return data


def _readings(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_READING
    username, password, region = _credentials(params)
    minutes = params.get("minutes", 120)
    max_count = params.get("maxCount", 24)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 1440:
        raise RpcError(-32602, "params.minutes 必须是 1..1440", {"code": "INVALID_INPUT"})
    if isinstance(max_count, bool) or not isinstance(max_count, int) or not 1 <= max_count <= 288:
        raise RpcError(-32602, "params.maxCount 必须是 1..288", {"code": "INVALID_INPUT"})
    try:
        import pydexcom
    except ModuleNotFoundError as exc:
        raise RpcError(
            -32000,
            "pydexcom 未安装；请先完成模块依赖安装",
            {"code": "DEPENDENCY_MISSING"},
        ) from exc
    try:
        dexcom = pydexcom.Dexcom(username, password, region=region)
        raw = dexcom.get_glucose_readings(minutes=minutes, max_count=max_count)
        readings = [adapter.normalize_reading(_reading_dict(item)) for item in raw or []]
    except (TypeError, ValueError) as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    except Exception as exc:
        raise RpcError(
            -32000,
            f"Dexcom 读取失败：{type(exc).__name__}",
            {"code": "MODULE_ERROR"},
        ) from exc
    if not readings:
        return {"available": False, "readings": [], "summary": None, "nonDiagnostic": NON_DIAGNOSTIC}
    summary = adapter.summarize_readings(readings)
    _LAST_READING = {"available": True, **adapter.to_record(readings[-1])}
    return {
        "available": True,
        "readings": [adapter.to_record(item) for item in readings],
        "summary": summary,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Dexcom CGM",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "readings", "latestReading", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return {"ok": True, "warm": True, "dependency": "pydexcom"}
    if method == "health":
        return {
            "ok": True,
            "warm": True,
            "pydexcomAvailable": importlib.util.find_spec("pydexcom") is not None,
            "requiresNetwork": True,
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "readings":
        return _readings(params)
    if method == "latestReading":
        if _LAST_READING is None:
            return {"available": False, "valueMgdl": 0, "nonDiagnostic": NON_DIAGNOSTIC}
        return _LAST_READING
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
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

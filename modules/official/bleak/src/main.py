"""BLE Health 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``readHeartRate`` / ``readWeight`` /
``parseCapture`` / ``latestSample`` / ``deactivate``。

bleak 只在读取设备时导入；``parseCapture`` 可离线回放十六进制 GATT 字节，便于测试。
设备地址不写入返回值和日志。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.hbldh.bleak")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_UUID = "00002a9c-0000-1000-8000-00805f9b34fb"
_LAST_SAMPLE: dict[str, Any] | None = None


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _address(params: dict[str, Any]) -> str:
    value = params.get("address")
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 64:
        raise RpcError(-32602, "params.address 必须是 BLE 设备地址", {"code": "INVALID_INPUT"})
    return value.strip()


def _timeout(params: dict[str, Any]) -> float:
    value = params.get("timeoutS", 10)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 60:
        raise RpcError(-32602, "params.timeoutS 必须在 1..60 秒", {"code": "INVALID_INPUT"})
    return float(value)


def _read_characteristic(address: str, characteristic: str, timeout: float) -> bytes:
    try:
        import bleak
    except ModuleNotFoundError as exc:
        raise RpcError(
            -32000,
            "bleak 未安装；请先完成模块依赖安装",
            {"code": "DEPENDENCY_MISSING"},
        ) from exc

    async def read() -> bytes:
        async with bleak.BleakClient(address, timeout=timeout) as client:
            return bytes(await client.read_gatt_char(characteristic))

    try:
        return asyncio.run(read())
    except Exception as exc:
        raise RpcError(
            -32000,
            f"BLE 读取失败：{type(exc).__name__}",
            {"code": "MODULE_ERROR"},
        ) from exc


def _heart_rate_sample(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_SAMPLE
    raw = _read_characteristic(_address(params), HEART_RATE_UUID, _timeout(params))
    try:
        parsed = adapter.parse_heart_rate_measurement(raw)
    except ValueError as exc:
        raise RpcError(-32000, str(exc), {"code": "MODULE_ERROR"}) from exc
    sample = {
        "heartRate": parsed["heartRate"],
        "rrIntervalsMs": parsed["rrIntervalsMs"],
        "measuredAt": _now(),
        "source": "ble",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    _LAST_SAMPLE = {"available": True, **sample}
    return sample


def _weight_sample(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_SAMPLE
    raw = _read_characteristic(_address(params), BODY_COMPOSITION_UUID, _timeout(params))
    try:
        parsed = adapter.parse_body_composition_measurement(raw)
    except ValueError as exc:
        raise RpcError(-32000, str(exc), {"code": "MODULE_ERROR"}) from exc
    if parsed["weightKg"] is None:
        raise RpcError(-32000, "设备未返回体重字段", {"code": "MODULE_ERROR"})
    sample = {
        "weightKg": parsed["weightKg"],
        "bodyFatPercent": parsed["bodyFatPercent"],
        "measuredAt": parsed.get("measuredAt") or _now(),
        "source": "ble",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    _LAST_SAMPLE = {"available": True, "heartRate": 0, **sample}
    return sample


def _parse_capture(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_SAMPLE
    kind = params.get("kind")
    raw_hex = params.get("dataHex")
    if kind not in {"heartRate", "weight"}:
        raise RpcError(-32602, "params.kind 必须是 heartRate 或 weight", {"code": "INVALID_INPUT"})
    if not isinstance(raw_hex, str):
        raise RpcError(-32602, "params.dataHex 必须是十六进制字符串", {"code": "INVALID_INPUT"})
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise RpcError(-32602, "params.dataHex 不是合法十六进制", {"code": "INVALID_INPUT"}) from exc
    try:
        if kind == "heartRate":
            parsed = adapter.parse_heart_rate_measurement(raw)
            sample = {
                "heartRate": parsed["heartRate"],
                "rrIntervalsMs": parsed["rrIntervalsMs"],
                "measuredAt": _now(),
                "source": "ble-capture",
                "nonDiagnostic": NON_DIAGNOSTIC,
            }
        else:
            parsed = adapter.parse_body_composition_measurement(raw)
            sample = {
                "weightKg": parsed["weightKg"],
                "bodyFatPercent": parsed["bodyFatPercent"],
                "measuredAt": parsed.get("measuredAt") or _now(),
                "source": "ble-capture",
                "nonDiagnostic": NON_DIAGNOSTIC,
            }
    except ValueError as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    _LAST_SAMPLE = {"available": True, **sample}
    return sample


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "BLE Health",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "readHeartRate", "readWeight", "parseCapture", "latestSample", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return {"ok": True, "warm": True, "dependency": "bleak"}
    if method == "health":
        return {
            "ok": True,
            "warm": True,
            "bleakAvailable": importlib.util.find_spec("bleak") is not None,
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "readHeartRate":
        return _heart_rate_sample(params)
    if method == "readWeight":
        return _weight_sample(params)
    if method == "parseCapture":
        return _parse_capture(params)
    if method == "latestSample":
        if _LAST_SAMPLE is None:
            return {"available": False, "heartRate": 0, "nonDiagnostic": NON_DIAGNOSTIC}
        return _LAST_SAMPLE
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

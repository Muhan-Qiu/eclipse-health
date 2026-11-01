"""BioSPPy ECG 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``analyze`` / ``stats`` / ``ecg.quality`` / ``deactivate``。
只暴露 ECG/HRV 子集。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from adapter import (
    NON_DIAGNOSTIC,
    AdapterError,
    build_summary,
    parse_rr,
    quality_from_rr,
    rpeaks_to_rr,
    widget_stats,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.scientisst.biosppy")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
MAX_SIGNAL_BYTES = 512 * 1024 * 1024


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


def _read_signal(ref: dict[str, Any]) -> Any:
    import numpy as np

    path = Path(str(ref.get("path") or ""))
    if not path.is_file():
        raise AdapterError("invalid_input", "signalRef.path 不是可读文件")
    if path.stat().st_size > MAX_SIGNAL_BYTES:
        raise AdapterError("invalid_input", "波形文件超过 512MB 上限")
    blob = path.read_bytes()
    expected = str(ref.get("sha256") or "")
    if expected and hashlib.sha256(blob).hexdigest() != expected:
        raise AdapterError("invalid_input", "波形文件校验失败")
    if len(blob) % 4 != 0:
        raise AdapterError("invalid_input", "波形文件不是 float32 数组")
    return np.frombuffer(blob, dtype="<f4").astype("float32")


def _require_fs(ref: dict[str, Any]) -> float:
    try:
        fs = float(ref.get("fs") or 0)
    except (TypeError, ValueError):
        fs = 0.0
    if fs <= 0:
        raise AdapterError("invalid_input", "signalRef.fs 缺失或非法")
    return fs


def _extract_rpeaks(result: Any) -> Any:
    try:
        return result["rpeaks"]
    except (TypeError, KeyError, IndexError):
        return getattr(result, "rpeaks", None)


def _analyze(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("rr") is not None:
        return build_summary(parse_rr(params.get("rr")), source="rr")

    ref = params.get("signalRef")
    if not isinstance(ref, dict):
        raise AdapterError("invalid_input", "需要 params.rr 或 params.signalRef")
    fs = _require_fs(ref)
    try:
        from biosppy.signals import ecg
    except ImportError:
        return {"error": {"code": "dependency_missing", "message": "模块 venv 中缺少 biosppy"}}

    samples = _read_signal(ref)
    try:
        out = ecg(signal=samples, sampling_rate=fs, show=False)
        peaks = _extract_rpeaks(out)
        rr = rpeaks_to_rr(list(peaks), fs)
        return build_summary(rr, n_peaks=len(peaks), source="biosppy")
    except AdapterError:
        raise
    except Exception as exc:  # noqa: BLE001 - 上游库异常转业务错误
        return {"error": {"code": "analysis_failed", "message": f"{type(exc).__name__}: {exc}"[:300]}}


def _health() -> dict[str, Any]:
    version = None
    try:
        import biosppy

        version = getattr(biosppy, "__version__", None)
    except ImportError:
        pass
    return {"ok": True, "library": "biosppy", "version": version, "nonDiagnostic": NON_DIAGNOSTIC}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "BioSPPy · ECG",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "analyze", "stats", "ecg.quality", "deactivate"],
            "health": _health(),
        }
    if method == "warmup":
        return _health()
    if method == "health":
        return _health()
    if method == "analyze":
        return _analyze(params)
    if method == "stats":
        return widget_stats(params.get("rr"))
    if method == "ecg.quality":
        return quality_from_rr(params.get("rr"))
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
        result = handle(str(method), params)
        _result(request_id, result)
        return method != "deactivate"
    except AdapterError as error:
        _error(request_id, RpcError(-32602, error.message, {"code": "INVALID_INPUT", "reason": error.code}))
        return True
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
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

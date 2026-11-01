"""BrainFlow device-adapter 模块：stdio JSON-RPC 2.0，每行一条 JSON。

连接/采样时懒加载 ``brainflow``（含 numpy），因此 health/import/纯解析在未安装
依赖时仍可用。原始波形不返回、不写日志；只返回质量摘要。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (
    DISCLAIMER,
    AdapterError,
    boards_payload,
    channels_for,
    compute_signal_quality,
    records_from_jsonl,
    resolve_board,
    summarize_quality,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.brainflow-dev.brainflow")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "brainflow"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "boards.list",
    "connect",
    "snapshot",
    "disconnect",
    "import",
    "stats",
    "channels.list",
    "deactivate",
]

_session: dict[str, Any] = {"board": None, "shim": None, "sampleRate": None, "channels": None}
_lock = threading.Lock()


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
        "connected": _session["shim"] is not None,
        "note": DISCLAIMER,
    }


def _require_dependency() -> None:
    if not _dependency_available():
        raise RpcError(
            -32000,
            f"缺少依赖 {DEPENDENCY}；请让核心为模块 venv 安装 dependencies",
            {"code": "MODULE_DEPENDENCY_MISSING"},
        )


def _connect(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    try:
        name, board_id = resolve_board(params.get("board"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    port = params.get("serialPort")
    if port is not None and not isinstance(port, str):
        raise RpcError(-32602, "params.serialPort 必须是字符串", {"code": "INVALID_INPUT"})
    try:
        from brainflow.board_shim import BoardShim, BrainFlowInputParams

        inputs = BrainFlowInputParams()
        if isinstance(port, str) and port.strip():
            inputs.serial_port = port.strip()
        shim = BoardShim(board_id, inputs)
        shim.prepare_session()
        sample_rate = float(BoardShim.get_sampling_rate(board_id))
        channels = [str(item) for item in BoardShim.get_eeg_channels(board_id)]
    except Exception as exc:  # noqa: BLE001 - 硬件/驱动错误要可读
        return {
            "error": {
                "code": "hardware_unavailable",
                "message": f"板卡连接失败：{type(exc).__name__}",
            }
        }
    with _lock:
        _session.update(
            {"board": name, "shim": shim, "sampleRate": sample_rate, "channels": channels}
        )
    return {
        "connected": True,
        "board": name,
        "boardId": board_id,
        "sampleRate": sample_rate,
        "channels": channels,
        "note": DISCLAIMER,
    }


def _snapshot(params: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        shim = _session["shim"]
        board = _session["board"]
        sample_rate = _session["sampleRate"]
        channels = _session["channels"]
    if shim is None:
        return {"error": {"code": "not_connected", "message": "尚未连接板卡"}}
    seconds = params.get("seconds", 5)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 60:
        raise RpcError(-32602, "params.seconds 必须在 (0, 60] 内", {"code": "INVALID_INPUT"})
    try:
        frame = shim.get_current_board_data(int(sample_rate * float(seconds)))
        matrix = frame[channels].tolist()
        quality = compute_signal_quality(matrix)
    except Exception as exc:  # noqa: BLE001 - 采样失败返回可读错误
        return {"error": {"code": "hardware_unavailable", "message": f"采样失败：{type(exc).__name__}"}}
    return {
        "board": board,
        "sampleRate": sample_rate,
        "quality": quality,
        "note": DISCLAIMER,
    }


def _disconnect() -> dict[str, Any]:
    with _lock:
        shim = _session["shim"]
        _session.update({"board": None, "shim": None, "sampleRate": None, "channels": None})
    if shim is not None:
        try:
            shim.release_session()
        except Exception:  # noqa: BLE001, S110 - 释放失败不应阻塞卸载
            pass
    return {"ok": True, "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    payload = params.get("payload")
    if not isinstance(payload, str):
        raise RpcError(-32602, "params.payload 必须是 JSONL 字符串", {"code": "INVALID_INPUT"})
    try:
        records = records_from_jsonl(payload)
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def _quality_or_empty(params: dict[str, Any]) -> dict[str, Any]:
    quality = params.get("quality")
    if quality is None:
        return {"latest": {"quality": 0.0}, "channels": [], "ok": False, "note": DISCLAIMER}
    try:
        return summarize_quality(quality)
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "BrainFlow EEG/EMG Capture",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": CAPABILITIES,
            "health": health_payload(),
        }
    if method in {"warmup", "health"}:
        return health_payload()
    if method == "boards.list":
        return boards_payload()
    if method == "connect":
        return _connect(params)
    if method == "snapshot":
        return _snapshot(params)
    if method == "disconnect":
        return _disconnect()
    if method == "import":
        return _import(params)
    if method == "stats":
        return _quality_or_empty(params)
    if method == "channels.list":
        quality = params.get("quality")
        if quality is None:
            return {"items": [], "count": 0, "note": DISCLAIMER}
        try:
            return channels_for(quality)
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

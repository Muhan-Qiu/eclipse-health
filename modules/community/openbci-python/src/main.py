"""OpenBCI_Python device-adapter 模块：stdio JSON-RPC 2.0，每行一条 JSON。

上游 ``openbci`` 只在 ``stream.start`` 中懒加载；文本解析为纯标准库实现。
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
    channels_for,
    devices_payload,
    records_from_text,
    resolve_board,
    resolve_port,
    summarize_records,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.openbci-archive.openbci")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "openbci"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "devices.list",
    "ports.check",
    "stream.start",
    "stream.stop",
    "import",
    "stats",
    "channels.list",
    "deactivate",
]

_session: dict[str, Any] = {"board": None, "port": None, "streamer": None}
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
        "streaming": _session["streamer"] is not None,
        "note": DISCLAIMER,
    }


def _require_dependency() -> None:
    if not _dependency_available():
        raise RpcError(
            -32000,
            "缺少上游 openbci/pyserial；请让核心为模块 venv 安装 dependencies",
            {"code": "MODULE_DEPENDENCY_MISSING"},
        )


def _stream_start(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    try:
        board_name, _ = resolve_board(params.get("board", "cyton"))
        port = resolve_port(params.get("port"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    try:
        from openbci import cyton as bci

        board = bci.OpenBCICyton(port=port, daisy=board_name == "cyton-daisy")
        thread = threading.Thread(target=board.start_stream, daemon=True)
        thread.start()
    except Exception as exc:  # noqa: BLE001 - 硬件/串口错误要可读
        return {
            "error": {
                "code": "hardware_unavailable",
                "message": f"OpenBCI 连接失败：{type(exc).__name__}",
            }
        }
    with _lock:
        _session.update({"board": board_name, "port": port, "streamer": board})
    return {"streaming": True, "board": board_name, "port": port, "note": DISCLAIMER}


def _stream_stop() -> dict[str, Any]:
    with _lock:
        board = _session["streamer"]
        _session.update({"board": None, "port": None, "streamer": None})
    if board is not None:
        try:
            board.stop()
        except Exception:  # noqa: BLE001, S110 - 停止失败不应阻塞卸载
            pass
    return {"ok": True, "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    payload = params.get("payload")
    if not isinstance(payload, str):
        raise RpcError(-32602, "params.payload 必须是文本", {"code": "INVALID_INPUT"})
    try:
        result = records_from_text(
            payload,
            board=params.get("board", "cyton"),
            sample_rate=params.get("sampleRate", 250.0),
            captured_at=params.get("capturedAt") if isinstance(params.get("capturedAt"), str) else None,
        )
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {
        "records": result["records"],
        "count": len(result["records"]),
        "parsed": result["parsed"],
        "note": DISCLAIMER,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "OpenBCI Serial Capture",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": CAPABILITIES,
            "health": health_payload(),
        }
    if method in {"warmup", "health"}:
        return health_payload()
    if method == "devices.list":
        return devices_payload()
    if method == "ports.check":
        try:
            return {"valid": True, "port": resolve_port(params.get("port")), "note": DISCLAIMER}
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method == "stream.start":
        return _stream_start(params)
    if method == "stream.stop":
        return _stream_stop()
    if method == "import":
        return _import(params)
    if method == "stats":
        try:
            return summarize_records(params.get("records", []))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method == "channels.list":
        try:
            return channels_for(params.get("parsed", {}))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method in {"activate", "deactivate"}:
        _stream_stop()
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

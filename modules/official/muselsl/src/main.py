"""muselsl device-adapter 模块：stdio JSON-RPC 2.0，每行一条 JSON。

上游 CLI 在子进程中运行；CSV 解析为纯标准库实现，缺依赖时仍可 import。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (
    DISCLAIMER,
    AdapterError,
    build_stream_command,
    channels_for,
    devices_payload,
    records_from_csv,
    summarize_records,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.alexandrebarachant.muselsl")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "muselsl"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "devices.list",
    "stream.start",
    "stream.stop",
    "import",
    "stats",
    "channels.list",
    "deactivate",
]
_processes: list[subprocess.Popen[Any]] = []


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
        "runningStreams": sum(1 for process in _processes if process.poll() is None),
        "note": DISCLAIMER,
    }


def _require_dependency() -> None:
    if not _dependency_available():
        raise RpcError(
            -32000,
            f"缺少依赖 {DEPENDENCY}；请让核心为模块 venv 安装 dependencies",
            {"code": "MODULE_DEPENDENCY_MISSING"},
        )


def _stream_start(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    try:
        command = build_stream_command(params.get("preset", "muse-2"), params.get("address"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    executable = shutil.which(command[0])
    if executable is None:
        raise RpcError(-32000, "在模块 venv 中找不到 muselsl CLI",
                       {"code": "MODULE_DEPENDENCY_MISSING"})
    command[0] = executable
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise RpcError(-32000, f"启动 muselsl 失败：{type(exc).__name__}",
                       {"code": "UPSTREAM_ERROR"}) from exc
    _processes.append(process)
    return {"pid": process.pid, "command": [Path(part).name for part in command], "note": DISCLAIMER}


def _stream_stop() -> dict[str, Any]:
    stopped = 0
    for process in _processes:
        if process.poll() is None:
            process.terminate()
            stopped += 1
    _processes.clear()
    return {"stopped": stopped, "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    payload = params.get("payload")
    if not isinstance(payload, str):
        raise RpcError(-32602, "params.payload 必须是 CSV 字符串", {"code": "INVALID_INPUT"})
    try:
        result = records_from_csv(
            payload,
            params.get("preset", "muse-2"),
            params.get("capturedAt") if isinstance(params.get("capturedAt"), str) else None,
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
            "name": "Muse LSL Stream",
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

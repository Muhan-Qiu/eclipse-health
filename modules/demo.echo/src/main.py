"""Echo Demo：最小 stdio JSON-RPC 2.0 模块（每行一条 JSON）。

方法：initialize / hello / echo / fail / call_core / health / deactivate。
不依赖 eclipse_health_backend，安装包可直接在任意 Python 3.12 中运行。
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "")
PERMISSIONS = [item for item in os.environ.get("ECLIPSE_PERMISSIONS", "").split(",") if item]

_next_core_id = 9000


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, error: RpcError) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "error": {"code": error.code, "message": error.message}}
    if error.data is not None:
        payload["error"]["data"] = error.data
    _write(payload)


def _call_core(method: str, params: dict[str, Any]) -> Any:
    """向核心发起受限 RPC；仅用于自检权限拒绝路径。"""
    global _next_core_id
    request_id = _next_core_id
    _next_core_id += 1
    _write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    while True:
        line = sys.stdin.readline()
        if not line:
            raise RpcError(-32003, "core closed the channel", {"code": "MODULE_CRASH"})
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get("id") == request_id and "method" not in message:
            if "error" in message:
                error = message.get("error") or {}
                data = error.get("data") if isinstance(error.get("data"), dict) else {}
                raise RpcError(
                    int(error.get("code", -32000)),
                    str(error.get("message", "core call failed")),
                    data,
                )
            return message.get("result")
        # 核心在等待期间发来的其它请求：照常处理。
        if "method" in message and isinstance(message.get("id"), int):
            _dispatch_and_reply(message)


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    """处理一条请求；返回 False 表示收到 deactivate。"""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        result = handle(method, params)
        _result(request_id, result)
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Echo Demo",
            "moduleId": MODULE_ID,
            "apiVersion": params.get("apiVersion", API_VERSION),
            "permissions": PERMISSIONS,
            "capabilities": ["initialize", "hello", "echo", "fail", "call_core", "health", "deactivate"],
        }
    if method == "hello":
        name = str(params.get("name", "world"))[:64]
        return {"message": f"Hello, {name}!"}
    if method == "echo":
        text = params.get("text")
        if not isinstance(text, str):
            raise RpcError(-32602, "params.text must be a string", {"code": "INVALID_INPUT"})
        return {"text": text, "length": len(text)}
    if method == "fail":
        mode = params.get("mode", "error")
        if mode == "crash":
            os._exit(17)
        if mode == "timeout":
            time.sleep(30)
        raise RpcError(-32000, "demo failure", {"code": "MODULE_ERROR"})
    if method == "call_core":
        core_method = params.get("method")
        core_params = params.get("params") or {}
        if not isinstance(core_method, str) or not isinstance(core_params, dict):
            raise RpcError(-32602, "params.method must be a string", {"code": "INVALID_INPUT"})
        return _call_core(core_method, core_params)
    if method == "health":
        return {"ok": True}
    if method == "activate":
        return {"ok": True}
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


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
        if not isinstance(message, dict):
            continue
        if "method" not in message:
            continue
        if "id" not in message:
            # notification：只响应 health 类的无 id 请求没有意义，这里直接忽略。
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

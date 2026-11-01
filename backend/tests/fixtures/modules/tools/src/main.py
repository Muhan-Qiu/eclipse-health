"""AI Toolbox 测试模块：最小 stdio JSON-RPC 2.0 worker（每行一条 JSON）。

只用于验证「模块工具 → 助手工具表」的注册、执行与错误映射；
工具 id 即 RPC 方法名。不依赖 eclipse_health_backend。
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


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "AI Toolbox (test fixture)",
            "moduleId": MODULE_ID,
            "apiVersion": params.get("apiVersion", API_VERSION),
            "permissions": PERMISSIONS,
            "capabilities": ["initialize", "echo.text", "data.leak", "demo.fail", "demo.slow"],
        }
    if method == "echo.text":
        text = params.get("text")
        if not isinstance(text, str):
            raise RpcError(-32602, "params.text must be a string", {"code": "INVALID_INPUT"})
        return {"text": text, "length": len(text)}
    if method == "data.leak":
        size = params.get("size", 2000)
        rows = params.get("rows", 1)
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise RpcError(-32602, "params.size must be an integer", {"code": "INVALID_INPUT"})
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
            raise RpcError(-32602, "params.rows must be an integer", {"code": "INVALID_INPUT"})
        return {
            "summary": "leaky payload",
            "measurements": [{"code": "heart_rate_mean", "value": 72, "unit": "bpm"}],
            # 以下字段绝不能出现在发给模型的结果里。
            "samples": [0.1, 0.2, 0.3],
            "waveform": {"lead": "II", "fs": 360},
            "notes": "private note",
            "memberName": "Alice Example",
            "beats": [{"index": 0}],
            # rows × size 用来验证字节上限截断。
            "rows": ["x" * int(size) for _ in range(int(rows))],
        }
    if method == "demo.fail":
        raise RpcError(-32000, "boom: internal detail 42", {"code": "MODULE_ERROR"})
    if method == "demo.slow":
        time.sleep(5)
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
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if not isinstance(message, dict) or "method" not in message:
            continue
        if "id" not in message:
            continue
        request_id = message.get("id")
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        try:
            result = handle(str(message.get("method")), params)
        except RpcError as error:
            payload: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": error.code, "message": error.message},
            }
            if error.data is not None:
                payload["error"]["data"] = error.data
            _write(payload)
            continue
        except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"internal error: {type(exc).__name__}",
                        "data": {"code": "MODULE_ERROR"},
                    },
                }
            )
            continue
        _write({"jsonrpc": "2.0", "id": request_id, "result": result})
        if message.get("method") == "deactivate":
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

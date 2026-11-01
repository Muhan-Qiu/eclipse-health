"""Stage C 端到端验收模块：最小 stdio JSON-RPC 2.0 worker（每行一条 JSON）。

只服务 ``scripts/e2e_stage_c.py``：返回固定测试数据，页面表单只写进程内列表，
不碰真实健康记录，也不依赖 ``eclipse_health_backend``。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "")
PERMISSIONS = [item for item in os.environ.get("ECLIPSE_PERMISSIONS", "").split(",") if item]

# 页面表格的初始数据；提交后会追加到内存列表，worker 重启即复位。
_ROWS: list[dict[str, Any]] = [
    {"capturedAt": "2026-10-28T08:00:00Z", "value": 68.4, "note": "seed-a"},
    {"capturedAt": "2026-10-29T08:00:00Z", "value": 69.1, "note": "seed-b"},
]
_FORM_DEFAULTS: dict[str, Any] = {
    "note": "seed-note",
    "value": 70.2,
    "date": "2026-10-30",
    "done": False,
}
_calls = 0


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _required_text(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RpcError(-32602, f"params.{key} must be a non-empty string", {"code": "INVALID_INPUT"})
    return value


def _number(params: dict[str, Any], key: str) -> float:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RpcError(-32602, f"params.{key} must be a number", {"code": "INVALID_INPUT"})
    return float(value)


def handle(method: str, params: dict[str, Any]) -> Any:
    global _calls
    _calls += 1

    if method == "initialize":
        return {
            "name": "Stage C E2E Fixture",
            "moduleId": MODULE_ID,
            "apiVersion": params.get("apiVersion", API_VERSION),
            "permissions": PERMISSIONS,
            "capabilities": [
                "initialize",
                "health",
                "widget.stats",
                "widget.list",
                "page.form",
                "page.list",
                "page.submit",
                "e2e.echo",
            ],
        }
    if method == "health":
        return {
            "status": "ok",
            "moduleId": MODULE_ID,
            "permissions": PERMISSIONS,
            "rows": len(_ROWS),
        }
    if method == "widget.stats":
        days = params.get("days", 7)
        return {
            "latest": {"bpm": 72, "at": "2026-10-30T07:30:00Z"},
            "days": days if isinstance(days, int) and not isinstance(days, bool) else 7,
            "series": [{"value": 70}, {"value": 71}, {"value": 72}],
        }
    if method == "widget.list":
        return {
            "items": [
                {"label": "深睡", "value": "1h 42m"},
                {"label": "浅睡", "value": "4h 05m"},
                {"label": "心率", "value": "72 bpm"},
            ]
        }
    if method == "page.form":
        return dict(_FORM_DEFAULTS)
    if method == "page.list":
        return {"items": [dict(row) for row in _ROWS]}
    if method == "page.submit":
        note = _required_text(params, "note")
        value = _number(params, "value")
        day = params.get("date")
        day = day if isinstance(day, str) and day else "2026-10-30"
        row = {"capturedAt": f"{day}T00:00:00Z", "value": value, "note": note}
        _ROWS.append(row)
        return {
            "saved": True,
            "row": row,
            "done": bool(params.get("done", False)),
            "count": len(_ROWS),
        }
    if method == "e2e.echo":
        text = _required_text(params, "text")
        return {"text": text, "length": len(text), "calls": _calls}
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
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
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

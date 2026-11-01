"""uPlot-inspired trend widget: stdio JSON-RPC 2.0 worker (one JSON per line).

Methods: ``initialize`` / ``warmup`` / ``health`` / ``trend`` / ``summary`` /
``deactivate``. No upstream JavaScript is loaded; the module only normalizes
numeric series passed in by the caller.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import DISCLAIMER, normalize_series, summarize

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.leeoniya.uplot")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")


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


def health_payload() -> dict[str, Any]:
    return {"ok": True, "warm": True, "disclaimer": DISCLAIMER}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(
                -32004,
                f"unsupported apiVersion {requested[:32]}",
                {"code": "INCOMPATIBLE_API"},
            )
        return {
            "name": "uPlot trend widget",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "trend",
                "summary",
                "deactivate",
            ],
            "health": health_payload(),
            "disclaimer": DISCLAIMER,
        }
    if method in {"warmup", "health"}:
        return health_payload()
    if method == "trend":
        try:
            return normalize_series(
                params.get("points"),
                unit=str(params.get("unit") or ""),
                max_points=params.get("maxPoints", 600),
            )
        except (TypeError, ValueError) as exc:
            raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    if method == "summary":
        try:
            return summarize(params.get("points"), unit=str(params.get("unit") or ""))
        except (TypeError, ValueError) as exc:
            raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
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
    except Exception as exc:  # noqa: BLE001 - module boundary
        _error(
            request_id,
            RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}),
        )
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
        if not isinstance(message, dict) or "method" not in message:
            continue
        if "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

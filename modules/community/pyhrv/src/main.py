"""pyhrv HRV 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``analyze`` / ``stats`` / ``hrv.metrics`` / ``deactivate``。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from adapter import (
    NON_DIAGNOSTIC,
    AdapterError,
    build_summary,
    map_pyhrv_time,
    metric_rows,
    parse_rr,
    widget_stats,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.pgomes92.pyhrv")
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


def _upstream_time(rr: list[float]) -> tuple[dict[str, float | None] | None, str | None]:
    try:
        from pyhrv import time_domain as pyhrv_time
    except ImportError:
        return None, "模块 venv 中缺少 pyhrv"
    try:
        return map_pyhrv_time(pyhrv_time.time_domain(nni=rr, plot=False)), None
    except TypeError:
        try:
            return map_pyhrv_time(pyhrv_time.time_domain(nni=rr)), None
        except Exception as exc:  # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"[:300]
    except Exception as exc:  # noqa: BLE001 - 上游库异常转业务错误
        return None, f"{type(exc).__name__}: {exc}"[:300]


def _analyze(params: dict[str, Any]) -> dict[str, Any]:
    rr = parse_rr(params.get("rr"))
    result = build_summary(rr)
    upstream, error = _upstream_time(rr)
    if upstream is not None:
        result["upstreamTime"] = upstream
    elif error:
        result["upstreamError"] = error
    return result


def _health() -> dict[str, Any]:
    version = None
    try:
        import pyhrv

        version = getattr(pyhrv, "__version__", None)
    except ImportError:
        pass
    return {"ok": True, "library": "pyhrv", "version": version, "nonDiagnostic": NON_DIAGNOSTIC}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "pyhrv · HRV 工具箱",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "analyze", "stats", "hrv.metrics", "deactivate"],
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
    if method == "hrv.metrics":
        rr = parse_rr(params.get("rr"))
        upstream, error = _upstream_time(rr)
        if upstream is not None:
            return {"metrics": upstream, "rows": metric_rows(upstream), "nonDiagnostic": NON_DIAGNOSTIC}
        return {"error": {"code": "dependency_missing", "message": error or "pyhrv unavailable"}}
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

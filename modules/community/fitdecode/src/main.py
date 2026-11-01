"""FIT Decoder 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``summary`` / ``importFile`` /
``latestSummary`` / ``deactivate``。上游 fitdecode 在调用时才导入，缺依赖返回
``DEPENDENCY_MISSING``，不影响 health/initialize。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.polyvertex.fitdecode")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
MAX_RECORDS = 5000


def _load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location(
        f"{MODULE_ID}.adapter", Path(__file__).with_name("adapter.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover - 安装包缺失时
        raise RuntimeError("adapter.py 缺失")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()
_LAST_SUMMARY: dict[str, Any] | None = None


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


def _dependency_available() -> bool:
    return importlib.util.find_spec("fitdecode") is not None


def _require_path(params: dict[str, Any]) -> Path:
    raw = params.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.path 必须是文件路径", {"code": "INVALID_INPUT"})
    path = Path(raw)
    if not path.is_file():
        raise RpcError(-32602, "文件不存在或不可读", {"code": "INVALID_INPUT"})
    return path


def _read_records(path: Path, max_records: int) -> list[dict[str, Any]]:
    try:
        import fitdecode
    except ModuleNotFoundError as exc:
        raise RpcError(
            -32000,
            "fitdecode 未安装；请先完成模块依赖安装",
            {"code": "DEPENDENCY_MISSING"},
        ) from exc
    records: list[dict[str, Any]] = []
    with fitdecode.FitReader(str(path)) as fit:
        for frame in fit:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                continue
            fields = {field.name: field.value for field in frame.fields}
            records.append(adapter.normalize_fit_record(fields))
            if len(records) >= max_records:
                break
    return records


def _import(params: dict[str, Any], *, include_records: bool) -> dict[str, Any]:
    global _LAST_SUMMARY
    path = _require_path(params)
    max_records = params.get("maxRecords", MAX_RECORDS)
    if not isinstance(max_records, int) or not 1 <= max_records <= MAX_RECORDS:
        raise RpcError(-32602, "params.maxRecords 必须是 1..5000", {"code": "INVALID_INPUT"})
    records = _read_records(path, max_records)
    try:
        summary = adapter.summarize_records(records)
    except ValueError as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    _LAST_SUMMARY = summary
    result: dict[str, Any] = {
        "summary": summary,
        "record": adapter.session_payload(summary),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    if include_records:
        result["records"] = records
        result["truncated"] = len(records) >= max_records
    return result


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "FIT Decoder",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "summary", "importFile", "latestSummary", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return {"ok": True, "warm": True, "dependency": "fitdecode"}
    if method == "health":
        return {
            "ok": True,
            "warm": True,
            "fitdecodeAvailable": _dependency_available(),
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "summary":
        return _import(params, include_records=False)
    if method == "importFile":
        return _import(params, include_records=True)
    if method == "latestSummary":
        if _LAST_SUMMARY is None:
            return {"available": False, "distanceKm": 0, "nonDiagnostic": NON_DIAGNOSTIC}
        return {"available": True, **_LAST_SUMMARY}
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

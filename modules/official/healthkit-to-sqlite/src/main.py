"""healthkit-to-sqlite 适配模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：initialize / warmup / health / import.healthkit / import.summary / deactivate。

只用 stdlib 解析 export.zip / export.xml；不 import 上游 sqlite-utils，不写数据库。
大结果写临时文件并返回 ``resultRef``；日志不记录记录内容与路径。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.dogsheep.healthkit-to-sqlite")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
RESULT_INLINE_LIMIT_BYTES = 3_500_000
RETURN_RECORD_LIMIT = 2_000
DISCLAIMER = "非医疗器械，不用于诊断。"

_last_summary: dict[str, Any] = {"count": 0, "counts": {}}


def _load_adapter() -> Any:
    name = "eh_adapter_" + MODULE_ID.replace(".", "_").replace("-", "_")
    path = Path(__file__).resolve().with_name("adapter.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter.py unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


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


def _shrink(result: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(result, ensure_ascii=False).encode("utf-8")
    if len(blob) <= RESULT_INLINE_LIMIT_BYTES:
        return result
    directory = Path(tempfile.mkdtemp(prefix="eh-healthkit-"))
    target = directory / "import.result.json"
    target.write_bytes(blob)
    return {
        "resultRef": {
            "path": str(target),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        },
        "summary": result.get("summary"),
        "disclaimer": DISCLAIMER,
    }


def _import(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.path 必须是非空路径", {"code": "INVALID_INPUT"})
    limit = params.get("limit", adapter.MAX_RECORDS_DEFAULT)
    try:
        parsed = adapter.read_export(raw, limit)
    except adapter.HealthExportError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    records = parsed["records"]
    summary = {
        "count": parsed["count"],
        "truncated": parsed["truncated"],
        "counts": parsed["counts"],
    }
    _last_summary.update(summary)
    return _shrink(
        {
            "summary": summary,
            "records": records[:RETURN_RECORD_LIMIT],
            "recordsTruncated": len(records) > RETURN_RECORD_LIMIT,
            "disclaimer": DISCLAIMER,
        }
    )


def health_payload() -> dict[str, Any]:
    return {"ok": True, "upstreamAvailable": True, "parser": "stdlib", "disclaimer": DISCLAIMER}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, "unsupported apiVersion", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "Apple Health 导入",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "import.healthkit",
                "import.summary",
                "deactivate",
            ],
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "import.healthkit":
        return _import(params)
    if method == "import.summary":
        return {**_last_summary, "disclaimer": DISCLAIMER}
    if method in {"activate"}:
        return {"ok": True}
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
        _result(request_id, handle(str(method), params))
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

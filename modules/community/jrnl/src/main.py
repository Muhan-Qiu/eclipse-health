"""jrnl 适配模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：initialize / warmup / health / journal.list / journal.get / journal.summary /
journal.search / deactivate。

上游 CLI 通过 ``JRNL_BINARY``（默认 ``jrnl``）子进程调用 ``--export json``；
``params.text`` 可直接传入导出 JSON，便于离线/单测。日记内容不写日志、不外发。
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

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.jrnl-org.jrnl")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DISCLAIMER = "非医疗器械，不用于诊断。"


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


def _binary() -> str:
    return os.environ.get("JRNL_BINARY", "jrnl")


def _export_text() -> str:
    binary = _binary()
    if shutil.which(binary) is None:
        raise RpcError(-32000, f"未找到 jrnl 可执行文件（{binary}）", {"code": "upstream_unavailable"})
    try:
        completed = subprocess.run(
            [binary, "--export", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RpcError(-32000, f"jrnl 调用失败：{type(exc).__name__}", {"code": "upstream_failed"}) from exc
    if completed.returncode != 0:
        raise RpcError(-32000, f"jrnl 退出码 {completed.returncode}", {"code": "upstream_failed"})
    return completed.stdout


def _entries(params: dict[str, Any]) -> list[dict[str, Any]]:
    text = params.get("text")
    source = text if isinstance(text, str) else _export_text()
    try:
        entries = adapter.parse_export(source)
    except adapter.JournalError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    limit = params.get("limit")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        return entries[: min(limit, 100)]
    return entries


def health_payload() -> dict[str, Any]:
    binary = _binary()
    return {
        "ok": True,
        "upstreamAvailable": shutil.which(binary) is not None,
        "binary": binary,
        "disclaimer": DISCLAIMER,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, "unsupported apiVersion", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "jrnl 日记",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "journal.list",
                "journal.get",
                "journal.summary",
                "journal.search",
                "deactivate",
            ],
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "journal.list":
        entries = _entries(params)
        return {"entries": entries, "summary": adapter.summarize(entries), "disclaimer": DISCLAIMER}
    if method == "journal.summary":
        return {**adapter.summarize(_entries(params)), "disclaimer": DISCLAIMER}
    if method == "journal.get":
        title = params.get("title")
        if not isinstance(title, str) or not title.strip():
            raise RpcError(-32602, "params.title 必须是非空字符串", {"code": "INVALID_INPUT"})
        entries = _entries(params)
        match = next((item for item in entries if item["title"] == title.strip()), None)
        if match is None:
            raise RpcError(-32602, "未找到匹配标题的日记", {"code": "not_found"})
        return {**match, "disclaimer": DISCLAIMER}
    if method == "journal.search":
        entries = _entries(params)
        query = params.get("query")
        tags = params.get("tags") if isinstance(params.get("tags"), list) else None
        limit = params.get("limit", 20)
        try:
            matches = adapter.search(entries, query, tags=tags, limit=limit)
        except adapter.JournalError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
        return {"matches": matches, "count": len(matches), "disclaimer": DISCLAIMER}
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

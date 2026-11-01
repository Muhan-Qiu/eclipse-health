"""导入 Agent 审计：JSONL 为准，``audit_log`` 表尽力而为。

绝不写健康数据内容、原文片段、文件名以外的 PII；只记录 session、动作、计数、
耗时、错误码与 provider 类型。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..settings import get_settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MAX_FILE_BYTES = 10 * 1024 * 1024
_FORBIDDEN = {"value", "values", "payload", "records", "content", "text", "snippet", "code"}


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN:
                continue
            sanitized = _sanitize(item, depth + 1)
            if sanitized is not None:
                cleaned[key[:80]] = sanitized
        return cleaned
    if isinstance(value, list | tuple):
        return [item for item in (_sanitize(entry, depth + 1) for entry in value[:32]) if item is not None]
    return None


def _path() -> Path:
    directory = get_settings().audit_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "import-agent.jsonl"


def _append_jsonl(event: str, session_id: str, detail: dict[str, Any] | None) -> None:
    path = _path()
    line = json.dumps(
        {
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            "sessionId": session_id,
            "detail": _sanitize(detail or {}),
        },
        ensure_ascii=False,
    )
    with _LOCK:
        try:
            if path.exists() and path.stat().st_size > _MAX_FILE_BYTES:
                path.replace(path.with_suffix(".jsonl.1"))
        except OSError:
            pass
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _append_db(event: str, session_id: str, detail: dict[str, Any] | None) -> None:
    try:
        from ..db.base import session_scope
        from ..modules import audit

        with session_scope() as session:
            audit.append(
                session,
                f"import_agent.{event}"[:64],
                scope=session_id[:64],
                detail=_sanitize(detail or {}),
            )
    except Exception:
        logger.debug("import-agent db audit unavailable", exc_info=True)


def record(event: str, session_id: str, detail: dict[str, Any] | None = None) -> None:
    """记录一次可观测事件；失败只记日志，不抛给调用方。"""
    try:
        _append_jsonl(event, session_id, detail)
    except Exception:  # noqa: BLE001
        logger.warning("import-agent audit write failed event=%s", event)
    _append_db(event, session_id, detail)


__all__ = ["record"]

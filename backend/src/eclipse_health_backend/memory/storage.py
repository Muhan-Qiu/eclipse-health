"""``<EH_DATA_DIR>/memory.json`` 的读写。

隐私：内容只在本机文件里，不写日志、不做遥测；助手只有在 ``enabled`` 为真时才
通过 :func:`memory_context` 拿到文本。文件损坏或不存在时一律回退为空文档，
坏数据不应阻断助手或档案页。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from ..domain.common import utc_now
from ..settings import get_settings
from .models import MemoryDocument, MemoryUpdate


def _memory_path() -> Path:
    return get_settings().data_dir / "memory.json"


def read_memory() -> MemoryDocument:
    path = _memory_path()
    try:
        raw = path.read_text(encoding="utf-8")
        return MemoryDocument.model_validate(json.loads(raw))
    except (OSError, ValueError, TypeError, ValidationError):
        return MemoryDocument()


def write_memory(update: MemoryUpdate) -> MemoryDocument:
    document = MemoryDocument(
        content=update.content,
        enabled=update.enabled,
        updatedAt=utc_now(),
    )
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return document


def memory_context() -> str:
    """返回可注入助手的文本；``enabled=false`` 或内容为空时返回空字符串。"""
    document = read_memory()
    if not document.enabled:
        return ""
    return document.content


__all__ = ["memory_context", "read_memory", "write_memory"]

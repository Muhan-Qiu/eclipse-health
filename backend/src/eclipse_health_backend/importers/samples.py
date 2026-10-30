"""内置示例记录：MIT-BIH 100/200/208。

只读白名单，不接收用户路径；解析仍走 ``importers`` 的 WFDB 适配器，
记录上标记 ``sampleId`` / ``isSample``，绝不伪装成用户数据。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session

from ..domain.errors import not_found
from ..settings import BACKEND_ROOT
from .base import ImportSource, ParseParameters
from .persist import create_record_from_parsed
from .registry import AdapterRegistry

logger = logging.getLogger(__name__)

SAMPLES_DIR = BACKEND_ROOT / "resources" / "samples"
SAMPLE_IDS: dict[str, str] = {
    "mitdb-100": "100",
    "mitdb-200": "200",
    "mitdb-208": "208",
}


def sample_prefix(sample_id: str) -> Path:
    """白名单样本的 WFDB 前缀；不存在则按 404 处理。"""
    name = SAMPLE_IDS.get(sample_id)
    prefix = SAMPLES_DIR / name if name else None
    if prefix is None or not prefix.with_suffix(".hea").is_file():
        raise not_found("sample", sample_id)
    return prefix


def import_sample(
    session: Session,
    registry: AdapterRegistry,
    *,
    sample_id: str,
    member_id: str,
    captured_at: datetime,
    timezone: str = "UTC",
    tags: list[str] | None = None,
    notes: str = "",
) -> Any:
    prefix = sample_prefix(sample_id)
    source = ImportSource(
        kind="sample",
        path=prefix.with_suffix(".hea"),
        workspace=prefix.parent,
        original_name=None,
        file_name_hash="",
        file_hash=_sample_hash(prefix),
    )
    adapter, _detection = registry.detect(source, "auto")
    parsed = adapter.parse(source, ParseParameters())
    return create_record_from_parsed(
        session,
        parsed,
        member_id=member_id,
        captured_at=captured_at,
        timezone=timezone,
        module_id=adapter.adapter_id,
        tags=tags,
        notes=notes,
        file_hash=source.file_hash,
        extra_metadata={"sampleId": sample_id, "isSample": True},
    )


def _sample_hash(prefix: Path) -> str:
    from . import store

    try:
        return store.hash_path_source(prefix.with_suffix(".hea"))
    except OSError:
        return ""


__all__ = ["SAMPLES_DIR", "SAMPLE_IDS", "import_sample", "sample_prefix"]

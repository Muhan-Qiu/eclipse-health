"""时间与 JSON 的通用小工具。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_storage_dt(value: datetime) -> datetime:
    """SQLModel 的 UTCDateTime 要求带时区，统一转成 UTC 再落库。"""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def from_storage_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_size_bytes(value: Any) -> int:
    return len(compact_json(value).encode("utf-8"))


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)

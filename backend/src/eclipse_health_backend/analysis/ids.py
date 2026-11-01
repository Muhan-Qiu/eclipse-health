"""ID 与时间小工具。

analysis 是纯库：不 import 后端的 db/api，也不依赖任何 ORM。
ID 规则见 ``docs/DATA_SCHEMA_V1.md`` §1：``<prefix>_<UUIDv7>``。
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime


def uuid7() -> uuid.UUID:
    """生成 UUIDv7（48 位毫秒时间 + 74 位随机），可按时间排序。"""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (((rand >> 62) & 0xFFF) << 64)
        | (0b10 << 62)
        | (rand & ((1 << 62) - 1))
    )
    return uuid.UUID(int=value)


def new_id(prefix: str) -> str:
    """返回 ``ana_...`` / ``msr_...`` 形式的 ID。"""
    return f"{prefix}_{uuid7()}"


def utcnow() -> datetime:
    return datetime.now(UTC)


def rfc3339(value: datetime) -> str:
    """RFC 3339，UTC，毫秒精度。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )

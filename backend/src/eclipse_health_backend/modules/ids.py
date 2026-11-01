"""ID 生成：UUIDv7（时间有序），与 DATA_SCHEMA_V1 §1 的 `<prefix>_<uuid>` 约定一致。"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """生成 UUIDv7：48 位毫秒时间戳 + version/variant + 随机位。"""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_bits = int.from_bytes(os.urandom(10), "big")
    value = (timestamp_ms << 80) | (0x7 << 76) | ((random_bits >> 62) << 64)
    value |= (0b10 << 62) | (random_bits & ((1 << 62) - 1))
    return uuid.UUID(int=value)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid7().hex}"


def audit_event_id() -> str:
    return prefixed_id("evt")

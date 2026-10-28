"""ID 生成：``<prefix>_<UUIDv7>``（Schema §1 / Q37）。

Python 3.12 标准库没有 UUIDv7，这里按 RFC 9562 实现最小的生成器：
48 位毫秒时间戳 + version 7 + 74 位随机数。同一毫秒内的顺序不保证，
分页排序以 ``capturedAt`` 为准，ID 只用于粗排序与去重。
"""

from __future__ import annotations

import re
import time
import uuid

PREFIXES: dict[str, str] = {
    "member": "mem",
    "record": "rec",
    "signal": "sig",
    "analysis": "ana",
    "measurement": "msr",
    "annotation": "ann",
    "report": "rep",
    "module": "mod",
    "audit": "evt",
}

_UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

ID_PATTERNS: dict[str, re.Pattern[str]] = {
    prefix: re.compile(rf"^{prefix}_{_UUID_RE}$") for prefix in PREFIXES.values()
}


def uuid7(*, timestamp_ms: int | None = None, rand_bytes: bytes | None = None) -> uuid.UUID:
    """生成 UUIDv7。可注入时间与随机字节，便于测试。"""
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if rand_bytes is None:
        rand_bytes = uuid.uuid4().bytes
    elif len(rand_bytes) < 10:
        raise ValueError("rand_bytes 至少需要 10 字节")

    rand_a = int.from_bytes(rand_bytes[0:2], "big") & 0x0FFF
    rand_b = int.from_bytes(rand_bytes[2:10], "big") & ((1 << 62) - 1)
    value = (
        ((timestamp_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


def prefix_for(kind: str) -> str:
    try:
        return PREFIXES[kind]
    except KeyError as exc:  # pragma: no cover - 调用方都是字面量
        raise ValueError(f"unknown id kind: {kind}") from exc


def new_id(kind: str) -> str:
    """``new_id("record") -> "rec_0192f3..."``"""
    return f"{prefix_for(kind)}_{uuid7()}"


def is_valid_id(value: str, kind: str) -> bool:
    return bool(ID_PATTERNS[prefix_for(kind)].match(value))


def id_pattern_regex(kind: str) -> str:
    """给 Pydantic ``pattern=`` 用的正则字符串。"""
    return ID_PATTERNS[prefix_for(kind)].pattern


def uuid7_timestamp_ms(value: uuid.UUID) -> int:
    if value.version != 7:
        raise ValueError("not a UUIDv7")
    return value.int >> 80


__all__ = [
    "ID_PATTERNS",
    "PREFIXES",
    "id_pattern_regex",
    "is_valid_id",
    "new_id",
    "prefix_for",
    "uuid7",
    "uuid7_timestamp_ms",
]

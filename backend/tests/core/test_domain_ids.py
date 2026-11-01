from __future__ import annotations

import uuid

import pytest

from eclipse_health_backend.domain.ids import (
    ID_PATTERNS,
    is_valid_id,
    new_id,
    prefix_for,
    uuid7,
    uuid7_timestamp_ms,
)


def test_uuid7_layout() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122
    assert len(value.bytes) == 16


def test_uuid7_embeds_timestamp() -> None:
    timestamp_ms = 1_724_000_000_123
    value = uuid7(timestamp_ms=timestamp_ms)
    assert uuid7_timestamp_ms(value) == timestamp_ms


def test_uuid7_is_time_sortable() -> None:
    earlier = uuid7(timestamp_ms=1_000, rand_bytes=b"\x00" * 10)
    later = uuid7(timestamp_ms=2_000, rand_bytes=b"\x00" * 10)
    assert earlier < later


def test_uuid7_uses_injected_randomness() -> None:
    first = uuid7(timestamp_ms=5_000, rand_bytes=b"\x11" * 10)
    second = uuid7(timestamp_ms=5_000, rand_bytes=b"\x22" * 10)
    assert first != second
    assert uuid7_timestamp_ms(first) == 5_000


@pytest.mark.parametrize("kind", ["member", "record", "signal", "analysis", "module", "audit"])
def test_new_id_format(kind: str) -> None:
    value = new_id(kind)
    prefix = prefix_for(kind)
    assert value.startswith(f"{prefix}_")
    assert ID_PATTERNS[prefix].match(value)
    assert is_valid_id(value, kind)


def test_new_ids_are_unique() -> None:
    values = {new_id("record") for _ in range(500)}
    assert len(values) == 500


def test_is_valid_id_rejects_wrong_prefix() -> None:
    record_id = new_id("record")
    assert not is_valid_id(record_id, "signal")
    assert not is_valid_id("rec_not-a-uuid", "record")
    assert not is_valid_id("", "record")


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError):
        new_id("unknown")

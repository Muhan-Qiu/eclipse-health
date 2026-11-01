"""ID 与时间工具。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from eclipse_health_backend.analysis import new_id, rfc3339, uuid7


def test_uuid7_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_new_id_prefix() -> None:
    assert new_id("ana").startswith("ana_")
    assert new_id("msr").count("_") == 1


def test_rfc3339_utc_milliseconds() -> None:
    stamp = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
    assert rfc3339(stamp) == "2026-01-02T03:04:05.678Z"

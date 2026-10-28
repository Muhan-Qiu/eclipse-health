from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from eclipse_health_backend.domain.common import utc_now
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.domain.models import (
    MAX_METADATA_BYTES,
    MAX_PAYLOAD_BYTES,
    TZDATA_AVAILABLE,
    HealthRecord,
    Member,
    Signal,
    SignalInput,
)


def make_member(**overrides) -> Member:
    now = utc_now()
    data = {
        "id": new_id("member"),
        "displayName": "本人",
        "createdAt": now,
        "updatedAt": now,
    }
    data.update(overrides)
    return Member(**data)


def make_record(**overrides) -> HealthRecord:
    now = utc_now()
    data = {
        "id": new_id("record"),
        "memberId": new_id("member"),
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    data.update(overrides)
    return HealthRecord(**data)


def test_member_defaults() -> None:
    member = make_member()
    assert member.sex == "unknown"
    assert member.notes == ""
    assert member.conditions == []
    dumped = member.model_dump(by_alias=True)
    assert dumped["schema"] == "org.eclipsehealth.member/1"
    assert "schema_ref" not in dumped


def test_member_display_name_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        make_member(displayName="   ")


def test_member_birth_year_bounds() -> None:
    with pytest.raises(ValidationError):
        make_member(birthYear=1800)


def test_record_defaults_and_schema_alias() -> None:
    record = make_record()
    assert record.unit == "mV"
    assert record.tags == []
    assert record.leads == []
    dumped = record.model_dump(by_alias=True, mode="json")
    assert dumped["schema"] == "org.eclipsehealth.record/1"
    assert dumped["timezone"] == "UTC"


def test_record_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        make_record(unexpectedField=1)


def test_record_captured_at_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        make_record(capturedAt=datetime(2026, 1, 1, 12, 0, 0))


def test_record_timezone_validated() -> None:
    with pytest.raises(ValidationError):
        make_record(timezone="Mars/Olympus")


@pytest.mark.skipif(not TZDATA_AVAILABLE, reason="tzdata unavailable on this machine")
def test_record_timezone_known_name() -> None:
    assert make_record(timezone="Asia/Shanghai").timezone == "Asia/Shanghai"


def test_record_type_namespace() -> None:
    with pytest.raises(ValidationError):
        make_record(recordType="ecg")
    assert make_record(recordType="io.github.someone.eeg").recordType


def test_record_tag_limits() -> None:
    with pytest.raises(ValidationError):
        make_record(tags=[f"t{i}" for i in range(33)])
    with pytest.raises(ValidationError):
        make_record(tags=["x" * 33])


def test_record_duplicate_tags_rejected() -> None:
    with pytest.raises(ValidationError):
        make_record(tags=["a", "a"])


def test_record_notes_limit() -> None:
    assert len(make_record(notes="x" * 4000).notes) == 4000
    with pytest.raises(ValidationError):
        make_record(notes="x" * 4001)


def test_record_metadata_limit() -> None:
    within = make_record(metadata={"blob": "x" * (MAX_METADATA_BYTES - 20)})
    assert within.metadata
    with pytest.raises(ValidationError):
        make_record(metadata={"blob": "x" * (MAX_METADATA_BYTES + 1)})


def test_record_payload_limit() -> None:
    within = make_record(payload={"blob": "x" * (MAX_PAYLOAD_BYTES - 20)})
    assert within.payload
    with pytest.raises(ValidationError):
        make_record(payload={"blob": "x" * (MAX_PAYLOAD_BYTES + 1)})


def test_record_leads_limits() -> None:
    leads = [f"L{i}" for i in range(16)]
    assert len(make_record(leads=leads).leads) == 16
    with pytest.raises(ValidationError):
        make_record(leads=[f"L{i}" for i in range(17)])
    with pytest.raises(ValidationError):
        make_record(leads=["I", "I"])


def test_signal_input_requires_exactly_one_source() -> None:
    SignalInput(lead="I", samples=[0.0, 1.0])
    SignalInput(lead="I", fileRef="wave.f32")
    with pytest.raises(ValidationError):
        SignalInput(lead="I")
    with pytest.raises(ValidationError):
        SignalInput(lead="I", samples=[0.0], fileRef="wave.f32")


def test_signal_shape_validation() -> None:
    now = utc_now()
    with pytest.raises(ValidationError):
        Signal(
            id=new_id("signal"),
            recordId=new_id("record"),
            lead="I",
            fs=500,
            shape=[0],
            storage={"relativePath": "signals/x.f32", "sha256": "a" * 64},
            createdAt=now,
        )


def test_signal_n_samples_property() -> None:
    now = utc_now()
    signal = Signal(
        id=new_id("signal"),
        recordId=new_id("record"),
        lead="I",
        fs=500,
        shape=[15000],
        storage={"relativePath": "signals/x.f32", "sha256": "a" * 64},
        createdAt=now,
    )
    assert signal.n_samples == 15000

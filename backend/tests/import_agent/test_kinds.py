"""候选记录规范（docs/HEALTH_RECORD_KINDS.md）。"""

from __future__ import annotations

import pytest

from eclipse_health_backend.import_agent.errors import RecordValidationError
from eclipse_health_backend.import_agent.kinds import external_id, normalize_record

FILES = {"export.csv", "report.pdf"}


def _base(**overrides):
    record = {
        "kind": "heart-rate",
        "value": 72,
        "unit": "bpm",
        "startAt": "2026-10-30T08:00:00+08:00",
        "source": {"kind": "app", "app": "Test"},
        "evidence": {"file": "export.csv", "line": 3, "snippet": "72"},
        "confidence": 0.9,
    }
    record.update(overrides)
    return record


def _reject(record, code: str | None = None):
    with pytest.raises(RecordValidationError) as exc:
        normalize_record(record, files=FILES)
    if code:
        assert exc.value.code == code
    return exc.value


def test_heart_rate_normalizes_bpm() -> None:
    record = normalize_record(_base(), files=FILES)
    assert record["unit"] == "count/min"
    assert record["recordType"] == "org.eclipsehealth.health.heart-rate"
    assert record["value"] == 72
    assert record["payload"]["evidence"]["line"] == 3
    assert record["id"].startswith("prp_")
    assert len(record["fingerprint"]) == 64


def test_blood_pressure_converts_kpa() -> None:
    record = normalize_record(
        _base(
            kind="blood-pressure",
            value={"systolic": 16, "diastolic": 10.7},
            unit="kPa",
        ),
        files=FILES,
    )
    assert record["unit"] == "mm[Hg]"
    assert record["value"] == {"systolic": 120.00992, "diastolic": 80.256634}


def test_blood_pressure_rejects_inverted_values() -> None:
    error = _reject(
        _base(kind="blood-pressure", value={"systolic": 80, "diastolic": 120}, unit="mmHg"),
        "invalid_value",
    )
    assert "systolic" in error.message


def test_sleep_requires_end_at() -> None:
    _reject(_base(kind="sleep", value="asleep-deep", unit="1"), "invalid_record")
    record = normalize_record(
        _base(
            kind="sleep",
            value="asleep-deep",
            unit="1",
            endAt="2026-10-30T09:00:00+08:00",
        ),
        files=FILES,
    )
    assert record["durationSec"] == 3600
    assert record["value"] == "asleep-deep"


def test_body_mass_converts_pounds() -> None:
    record = normalize_record(_base(kind="body-mass", value=154, unit="lbs"), files=FILES)
    assert record["unit"] == "kg"
    assert abs(record["value"] - 69.853225) < 1e-5


def test_temperature_converts_fahrenheit() -> None:
    record = normalize_record(
        _base(kind="body-temperature", value=98.6, unit="F"), files=FILES
    )
    assert record["unit"] == "Cel"
    assert abs(record["value"] - 37.0) < 1e-5


def test_hrv_requires_matching_unit() -> None:
    _reject(
        _base(kind="hrv", value={"metric": "rmssd", "value": 42}, unit="%"),
        "invalid_unit",
    )
    record = normalize_record(
        _base(kind="hrv", value={"metric": "rmssd", "value": 42}, unit="ms"),
        files=FILES,
    )
    assert record["metric"] == "rmssd"


def test_body_requires_a_metric() -> None:
    _reject(_base(kind="body", value={}, unit="1"), "invalid_record")
    record = normalize_record(
        _base(kind="body", value={"bodyFatPct": 18.5, "bmi": 22.1}, unit="1"),
        files=FILES,
    )
    assert record["value"]["bmi"] == 22.1


def test_ecg_without_waveform_is_rejected() -> None:
    error = _reject(
        _base(
            kind="ecg",
            value={"samplingRate": 500, "lead": "II"},
            unit="mV",
            evidence={"file": "report.pdf", "page": 1, "snippet": "ECG report"},
        ),
        "ecg_waveform_required",
    )
    assert "PDF" in error.message


def test_ecg_with_waveform_and_record_type() -> None:
    record = normalize_record(
        _base(
            kind="ecg",
            value={"samplingRate": 500, "lead": "II"},
            unit="mV",
            waveform={"file": "ecg.csv", "format": "csv", "column": 1, "timeColumn": 0},
        ),
        files=FILES,
    )
    assert record["recordType"] == "org.eclipsehealth.ecg"
    assert record["waveform"]["file"] == "ecg.csv"


def test_ecg_waveform_rejects_traversal() -> None:
    _reject(
        _base(
            kind="ecg",
            value={"samplingRate": 500},
            unit="mV",
            waveform={"file": "../../evil.csv"},
        ),
        "invalid_record",
    )


def test_evidence_must_reference_uploaded_file() -> None:
    _reject(_base(evidence={"file": "../secret.csv", "line": 1}), "evidence_file_unknown")


def test_evidence_needs_locator() -> None:
    _reject(_base(evidence={"file": "export.csv"}), "evidence_incomplete")


def test_unknown_kind_and_field() -> None:
    _reject(_base(kind="blood-oxygen"), "invalid_kind")
    _reject(_base(extra=1), "unexpected_field")


def test_invalid_time_order_and_confidence() -> None:
    _reject(_base(endAt="2026-10-30T07:00:00+08:00"), "invalid_record")
    _reject(_base(confidence=1.5), "invalid_record")
    _reject(_base(startAt="2026-10-30T08:00:00"), "invalid_record")


def test_duplicate_fingerprints_and_external_ids() -> None:
    first = normalize_record(_base(), files=FILES)
    second = normalize_record(_base(), files=FILES)
    assert first["fingerprint"] == second["fingerprint"]
    assert first["id"] != second["id"]

    eid_a = external_id(
        file_hash="sha256:abc",
        source={"kind": "app", "app": "Test"},
        kind="heart-rate",
        start_at="2026-10-30T08:00:00+08:00",
        end_at=None,
        value=72,
    )
    eid_b = external_id(
        file_hash="sha256:abc",
        source={"kind": "app", "app": "Test"},
        kind="heart-rate",
        start_at="2026-10-30T00:00:00Z",
        end_at=None,
        value=72,
    )
    assert eid_a == eid_b

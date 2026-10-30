"""Apple / Samsung / 华为：CSV/JSON 映射、BOM/时区、缺失字段 requires、实验标记。"""

from __future__ import annotations

import json

import numpy as np
import pytest
from import_helpers import BACKEND_ROOT, commit, csv_text, read_signal, upload_preview

VALUES = [round(float(value), 6) for value in np.sin(np.arange(20) / 3.0)]
APPLE_TIMES = [f"2026-10-28T10:00:{index / 512:09.6f}+08:00" for index in range(len(VALUES))]
B4_02_APPLE = (
    BACKEND_ROOT / "tests" / "fixtures" / "imports" / "apple" / "electrocardiograms.csv"
)


def _apple_csv(
    *,
    comment: str | None = "# Sampling Rate: 512 Hz",
    header: str = "Time,Voltage (mV)",
    times: list[str] | None = None,
) -> str:
    rows = [comment] if comment else []
    rows.append(header)
    stamps = times if times is not None else APPLE_TIMES
    for stamp, value in zip(stamps, VALUES):
        rows.append(f"{stamp},{value}")
    return "\n".join(rows) + "\n"


def _preview(client, name: str, payload: str | bytes, **form) -> dict:
    response = upload_preview(client, name, payload, **form)
    assert response.status_code == 200, response.text
    return response.json()


def test_apple_csv_with_bom_timezone_and_commit(client, default_member: dict) -> None:
    payload = ("﻿" + _apple_csv()).encode("utf-8")
    preview = _preview(client, "electrocardiograms.csv", payload)

    assert preview["format"] == "apple"
    assert preview["adapterId"] == "org.eclipsehealth.apple"
    assert preview["samplingRate"] == pytest.approx(512.0)
    assert preview["leads"] == ["I"]
    assert preview["durationSec"] == pytest.approx(len(VALUES) / 512)
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    codes = {item["code"] for item in preview["warnings"]}
    assert "experimental_format" in codes
    assert "lead_assumed" in codes

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["vendor"] == "Apple"
    assert record["metadata"]["verification"] == "experimental"
    assert record["metadata"]["startTime"] == "2026-10-28T10:00:00+08:00"
    np.testing.assert_allclose(
        read_signal(client, record["id"], "I"), VALUES, rtol=0, atol=1e-6
    )


def test_apple_single_voltage_column_uses_comment_rate(client, default_member: dict) -> None:
    rows = ["# Sampling Rate: 512 Hz", "Voltage (mV)"]
    rows += [f"{value}" for value in VALUES]
    preview = _preview(client, "apple_ecg.csv", "\n".join(rows) + "\n")
    assert preview["samplingRate"] == 512.0
    assert preview["requires"]["samplingRate"] is False
    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text


def test_apple_missing_sampling_rate_requires_correction(client, default_member: dict) -> None:
    payload = _apple_csv(comment=None, times=["0"] * len(VALUES))
    preview = _preview(client, "electrocardiograms.csv", payload)
    assert preview["samplingRate"] is None
    assert preview["requires"]["samplingRate"] is True

    missing = commit(client, preview["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "sampling_rate_required"

    response = commit(client, preview["importId"], default_member["id"], samplingRate=512)
    assert response.status_code == 201, response.text
    assert response.json()["record"]["samplingRate"] == 512.0


def test_apple_missing_voltage_column_is_invalid(client) -> None:
    payload = "# Sampling Rate: 512 Hz\nTime,HR\n0,70\n0.002,71\n"
    response = upload_preview(client, "electrocardiograms.csv", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_samsung_csv_requires_lead_and_records_experimental(
    client, default_member: dict
) -> None:
    rows = ["# Sampling Rate: 500 Hz", "timestamp,voltage,unit"]
    rows += [f"{index / 500:.6f},{value},mV" for index, value in enumerate(VALUES)]
    preview = _preview(client, "samsung_ecg.csv", "\n".join(rows) + "\n")

    assert preview["format"] == "samsung"
    assert preview["adapterId"] == "org.eclipsehealth.samsung"
    assert preview["samplingRate"] == pytest.approx(500.0)
    assert preview["leads"] == []
    assert preview["requires"] == {"samplingRate": False, "lead": True, "unit": False}
    assert any(item["code"] == "experimental_format" for item in preview["warnings"])

    missing = commit(client, preview["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "lead_required"

    response = commit(client, preview["importId"], default_member["id"], lead="I")
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["vendor"] == "Samsung"
    assert record["metadata"]["verification"] == "experimental"
    np.testing.assert_allclose(
        read_signal(client, record["id"], "I"), VALUES, rtol=0, atol=1e-6
    )


def test_samsung_json_mapping(client, default_member: dict) -> None:
    payload = {
        "device": "Samsung Galaxy Watch",
        "samplingRate": 500,
        "unit": "mV",
        "lead": "I",
        "samples": VALUES,
    }
    preview = _preview(client, "samsung_export.json", json.dumps(payload))
    assert preview["format"] == "samsung"
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    np.testing.assert_allclose(
        read_signal(client, response.json()["record"]["id"], "I"),
        VALUES,
        rtol=0,
        atol=1e-6,
    )


def test_huawei_json_requires_all_fields(client, default_member: dict) -> None:
    payload = {"device": "Huawei Watch D", "ecgData": VALUES}
    preview = _preview(client, "huawei_ecg.json", json.dumps(payload))
    assert preview["format"] == "huawei"
    assert preview["requires"] == {"samplingRate": True, "lead": True, "unit": True}
    assert any(item["code"] == "experimental_format" for item in preview["warnings"])

    missing = commit(client, preview["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "sampling_rate_required"

    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        samplingRate=500,
        unit="mV",
        lead="I",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["vendor"] == "Huawei"
    np.testing.assert_allclose(
        read_signal(client, record["id"], "I"), VALUES, rtol=0, atol=1e-6
    )


def test_plain_csv_still_uses_generic_adapter(client) -> None:
    text = csv_text(VALUES, header="time,MLII", time_step=0.002)
    preview = _preview(client, "ecg.csv", text)
    assert preview["format"] == "csv"
    assert preview["adapterId"] == "org.eclipsehealth.csv"


def test_identical_confidence_reports_candidates(client) -> None:
    payload = "# Samsung Health export\nTime,Lead I\n0.000,0.1\n0.002,0.2\n"
    response = upload_preview(client, "samsung_electrocardiogram.csv", payload)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "ambiguous_format"
    formats = {item["format"] for item in error["details"]["candidates"]}
    assert formats == {"apple", "samsung"}


def test_vendor_adapters_are_registered() -> None:
    from eclipse_health_backend.importers.registry import build_default_registry

    registry = build_default_registry()
    for fmt in ("edf", "scp-ecg", "apple", "samsung", "huawei"):
        adapter = registry.find(fmt)
        assert adapter is not None, fmt
        assert adapter.supported is True
        assert adapter.adapter_id.startswith("org.eclipsehealth.")


def test_b4_02_apple_fixture_infers_volts(client, default_member: dict) -> None:
    """B4-02 的合成 Apple 夹具以伏特存储，必须按量级推断为 V 再换算到 mV。"""
    if not B4_02_APPLE.exists():
        pytest.skip("B4-02 fixture not delivered")
    preview = _preview(client, "electrocardiograms.csv", B4_02_APPLE.read_bytes())
    assert preview["format"] == "apple"
    assert preview["samplingRate"] == pytest.approx(512.03, abs=0.1)
    assert preview["leads"] == ["I"]
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    assert any(item["code"] == "unit_inferred" for item in preview["warnings"])

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["sourceUnit"] == "V"
    samples = read_signal(client, record["id"], "I")
    assert samples.size == 5120
    assert samples[0] == pytest.approx(-0.145, abs=1e-3)

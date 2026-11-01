"""EDF/EDF+：合成夹具的正常/坏文件/单位校正/多导联/标注。"""

from __future__ import annotations

import numpy as np
import pytest
from format_builders import build_edf
from import_helpers import BACKEND_ROOT, commit, read_signal, upload_preview

FS = 500
N = 1000
SAMPLES = np.sin(np.arange(N) / 10.0) * 0.5
SECOND = np.cos(np.arange(N) / 12.0) * 0.3
REAL_SAMPLE = BACKEND_ROOT / "tests" / "fixtures" / "imports" / "edf" / "ecg-real.edf"
B4_02_TWO_LEAD = (
    BACKEND_ROOT / "tests" / "fixtures" / "imports" / "edf" / "mitdb100-2lead-10s.edf"
)
B4_02_NO_ECG = BACKEND_ROOT / "tests" / "fixtures" / "imports" / "edf" / "short_psg.edf"
B4_02_ANNOTATION_ONLY = (
    BACKEND_ROOT / "tests" / "fixtures" / "imports" / "edf" / "SC4001EC-Hypnogram.edf"
)


def _edf(channel_dimension: str = "mV", *, n_records: int = 2, extra_channels=None) -> bytes:
    channels = [
        {
            "label": "ECG MLII",
            "dimension": channel_dimension,
            "samples": SAMPLES,
        },
        {
            "label": "ECG V5",
            "dimension": channel_dimension,
            "samples": SECOND,
        },
    ]
    if extra_channels:
        channels.extend(extra_channels)
    return build_edf(channels, n_records=n_records, record_duration=N / FS / n_records)


def _preview(client, name: str, payload: bytes, **form) -> dict:
    response = upload_preview(client, name, payload, **form)
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_and_commit(client, default_member: dict) -> None:
    preview = _preview(client, "ecg.edf", _edf())
    assert preview["format"] == "edf"
    assert preview["adapterId"] == "org.eclipsehealth.edf"
    assert preview["samplingRate"] == FS
    assert preview["leads"] == ["MLII", "V5"]
    assert preview["durationSec"] == pytest.approx(2.0)
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    assert preview["preview"]["nSamples"] == N
    assert len(preview["preview"]["samples"]) == min(N, 2000)
    assert preview["preview"]["samples"][0] == pytest.approx(float(SAMPLES[0]), abs=2e-4)

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["leads"] == ["MLII", "V5"]
    assert record["samplingRate"] == FS
    assert record["metadata"]["verification"] == "verified"
    assert record["metadata"]["sourceUnit"] == "mV"

    np.testing.assert_allclose(
        read_signal(client, record["id"], "MLII"), SAMPLES, atol=2e-4
    )
    np.testing.assert_allclose(
        read_signal(client, record["id"], "V5"), SECOND, atol=2e-4
    )


def test_unknown_dimension_requires_unit_and_uv_conversion(
    client, default_member: dict
) -> None:
    preview = _preview(client, "unknown.edf", _edf("NU"))
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": True}
    assert any(item["code"] == "unknown_units" for item in preview["warnings"])

    missing = commit(client, preview["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "unit_required"

    response = commit(client, preview["importId"], default_member["id"], unit="uV")
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["sourceUnit"] == "uV"
    np.testing.assert_allclose(
        read_signal(client, record["id"], "MLII"), SAMPLES * 0.001, atol=2e-7
    )


def test_multi_rate_channel_is_skipped(client) -> None:
    odd = {"label": "ECG II", "dimension": "mV", "samples": np.zeros(N // 2)}
    payload = _edf(extra_channels=[odd])
    # 主记录 2 条、每记录 500 点；ECG II 每条记录只有 250 点 → 采样率不同。
    preview = _preview(client, "mixed.edf", payload)
    assert preview["leads"] == ["MLII", "V5"]
    assert any(item["code"] == "channel_rate_mismatch" for item in preview["warnings"])


def test_annotations_are_counted_but_not_leads(client) -> None:
    payload = build_edf(
        [
            {"label": "ECG I", "dimension": "mV", "samples": SAMPLES[:500]},
        ],
        n_records=1,
        record_duration=1.0,
        annotation_texts=["R", "N"],
    )
    preview = _preview(client, "annotated.edf", payload)
    assert preview["leads"] == ["I"]
    assert preview["hasAnnotations"] is True
    assert preview["annotationCount"] >= 1


def test_bad_header_is_invalid_file(client) -> None:
    payload = bytearray(_edf())
    payload[184:192] = b"00000100"
    response = upload_preview(client, "broken.edf", bytes(payload))
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_truncated_data_warns_and_keeps_complete_records(client) -> None:
    payload = _edf()
    truncated = payload[: len(payload) - 100]
    preview = _preview(client, "truncated.edf", truncated)
    assert preview["preview"]["nSamples"] == N // 2
    assert any(item["code"] == "truncated_records" for item in preview["warnings"])


def test_no_ecg_channel_is_rejected(client) -> None:
    payload = build_edf(
        [{"label": "EEG Fpz-Cz", "dimension": "uV", "samples": np.zeros(500)}],
        n_records=1,
        record_duration=1.0,
    )
    response = upload_preview(client, "eeg.edf", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_real_public_ecg_edf_is_verified(client, default_member: dict) -> None:
    payload = REAL_SAMPLE.read_bytes()
    preview = _preview(client, "ecg-real.edf", payload)
    assert preview["samplingRate"] == 1000.0
    assert preview["durationSec"] == pytest.approx(2.0)
    assert preview["leads"] == [
        "I",
        "II",
        "III",
        "aVR",
        "aVL",
        "aVF",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
    ]
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert len(record["leads"]) == 12
    assert record["metadata"]["verification"] == "verified"
    samples = read_signal(client, record["id"], "I")
    assert samples.size == 2000
    assert np.isfinite(samples).all()
    assert float(np.max(np.abs(samples))) < 5.0


def test_fixture_is_small() -> None:
    assert REAL_SAMPLE.is_file()
    assert REAL_SAMPLE.stat().st_size < 64 * 1024


def test_b4_02_derived_edf_is_imported(client, default_member: dict) -> None:
    if not B4_02_TWO_LEAD.exists():
        pytest.skip("B4-02 fixture not delivered")
    preview = _preview(client, "mitdb100-2lead-10s.edf", B4_02_TWO_LEAD.read_bytes())
    assert preview["samplingRate"] == 360.0
    assert preview["leads"] == ["MLII", "V5"]
    assert preview["durationSec"] == pytest.approx(10.0)
    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    assert read_signal(client, response.json()["record"]["id"], "MLII").size == 3600


def test_b4_02_non_ecg_and_annotation_only_edf_are_rejected(client) -> None:
    if not B4_02_NO_ECG.exists():
        pytest.skip("B4-02 fixture not delivered")
    no_ecg = upload_preview(client, "short_psg.edf", B4_02_NO_ECG.read_bytes())
    assert no_ecg.status_code == 422
    assert no_ecg.json()["code"] == "invalid_file"

    annotation_only = upload_preview(
        client, "SC4001EC-Hypnogram.edf", B4_02_ANNOTATION_ONLY.read_bytes()
    )
    assert annotation_only.status_code == 422
    assert annotation_only.json()["code"] == "invalid_file"

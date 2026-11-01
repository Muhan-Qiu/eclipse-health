"""WFDB 适配器：MIT-BIH 100/200/208 预览、提交、标注与非 360Hz 行为。"""

from __future__ import annotations

import shutil

import numpy as np
import pytest
from import_helpers import (
    API,
    SAMPLES_DIR,
    commit,
    expected_mv,
    path_preview,
    read_signal,
    sha256_tag,
    upload_preview,
    zip_samples,
)

from eclipse_health_backend.importers.base import ImportSource, ParseParameters
from eclipse_health_backend.importers.wfdb_adapter import WfdbImportAdapter

SAMPLE_ROWS = [
    ("100", ["MLII", "V5"]),
    ("200", ["MLII", "V1"]),
    ("208", ["MLII", "V1"]),
]


@pytest.mark.parametrize(("record", "leads"), SAMPLE_ROWS)
def test_preview_matches_header(client, samples_dir, record: str, leads: list[str]) -> None:
    response = path_preview(client, samples_dir / f"{record}.hea")
    assert response.status_code == 200, response.text
    preview = response.json()

    assert preview["format"] == "wfdb"
    assert preview["adapterId"] == "org.eclipsehealth.wfdb"
    assert preview["samplingRate"] == 360.0
    assert preview["leads"] == leads
    assert preview["durationSec"] == pytest.approx(650000 / 360)
    assert preview["preview"]["nSamples"] == 650000
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    assert len(preview["preview"]["samples"]) == 2000
    assert preview["preview"]["samples"][0] == pytest.approx(
        float(expected_mv(record, 0)[0]), abs=1e-9
    )
    assert preview["hasAnnotations"] is True
    assert preview["annotationCount"] > 0


def test_preview_folder_path(client, tmp_path) -> None:
    target = tmp_path / "record100"
    target.mkdir()
    for suffix in (".hea", ".dat", ".atr"):
        shutil.copy(SAMPLES_DIR / f"100{suffix}", target / f"100{suffix}")

    response = path_preview(client, target)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["samplingRate"] == 360.0
    assert preview["leads"] == ["MLII", "V5"]
    assert preview["preview"]["nSamples"] == 650000


def test_preview_zip_upload(client) -> None:
    response = upload_preview(client, "100.zip", zip_samples("100"))
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["format"] == "wfdb"
    assert preview["leads"] == ["MLII", "V5"]
    assert preview["fileNameHash"] == sha256_tag(b"100.zip")


def test_ambiguous_folder_is_rejected(client, samples_dir) -> None:
    response = path_preview(client, samples_dir)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "invalid_file"
    assert len(error["details"]["candidates"]) == 3


def test_corrupt_header_is_invalid_file(client, tmp_path) -> None:
    header = tmp_path / "bad.hea"
    header.write_text("bad 2 360 1000\nbad.dat 212 200 11 1024 995 -22131 0 MLII\n")
    response = path_preview(client, header)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


@pytest.mark.parametrize(("record", "leads"), SAMPLE_ROWS)
def test_commit_roundtrip_and_hashes(
    client, default_member: dict, data_dir, record: str, leads: list[str]
) -> None:
    archive = zip_samples(record)
    preview = upload_preview(client, f"{record}.zip", archive).json()
    import_id = preview["importId"]

    response = commit(client, import_id, default_member["id"], samplingRate=360, lead="MLII")
    assert response.status_code == 201, response.text
    body = response.json()
    record_body = body["record"]

    assert body["recordId"] == record_body["id"]
    assert record_body["recordType"] == "org.eclipsehealth.ecg"
    assert record_body["moduleId"] == "org.eclipsehealth.wfdb"
    assert record_body["leads"] == leads
    assert record_body["samplingRate"] == 360.0
    assert record_body["durationSec"] == pytest.approx(650000 / 360)
    assert record_body["unit"] == "mV"
    assert len(record_body["signalIds"]) == 2
    assert record_body["provenance"]["fileHash"] == sha256_tag(archive)
    assert record_body["provenance"]["fileNameHash"] == sha256_tag(f"{record}.zip".encode())
    assert record_body["provenance"]["adapterVersion"] == "1.0.0"
    assert record_body["metadata"]["hasAnnotations"] is True
    assert record_body["metadata"]["annotationCount"] > 0
    # 文件名不落库：只有哈希。
    assert f"{record}.zip" not in str(record_body)

    for lead, channel in zip(leads, range(len(leads))):
        samples = read_signal(client, record_body["id"], lead)
        expected = expected_mv(record, channel)
        assert samples.shape == expected.shape
        np.testing.assert_allclose(samples, expected, rtol=0, atol=1e-6)

    fetched = client.get(f"{API}/records/{record_body['id']}").json()
    assert fetched["signalIds"] == record_body["signalIds"]

    # commit 后工作区清理，重复 DELETE 仍为 204（幂等）。
    assert not (data_dir / "imports" / import_id).exists()
    assert client.delete(f"{API}/imports/{import_id}").status_code == 204


def test_multilead_signal_requires_lead(client, default_member: dict) -> None:
    preview = upload_preview(client, "100.zip", zip_samples("100")).json()
    record = commit(client, preview["importId"], default_member["id"]).json()["record"]

    response = client.get(f"{API}/records/{record['id']}/signal")
    assert response.status_code == 422
    assert response.json()["code"] == "lead_required"


def test_non_360hz_requires_confirmation(client, default_member: dict) -> None:
    import wfdb

    fs = 500
    count = 5000
    time = np.arange(count) / fs
    wave = 0.8 * np.sin(2 * np.pi * 1.2 * time) + 0.02 * np.cos(2 * np.pi * 12 * time)

    preview = path_preview(client, _write_wfdb(wfdb, fs=fs, wave=wave))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["samplingRate"] == 500.0
    assert body["requires"]["samplingRate"] is True
    assert any(item["code"] == "non_target_sampling_rate" for item in body["warnings"])

    missing = commit(client, body["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "sampling_rate_required"

    response = commit(
        client,
        body["importId"],
        default_member["id"],
        samplingRate=500,
        lead="II",
        unit="mV",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["samplingRate"] == 500.0
    assert record["durationSec"] == pytest.approx(count / fs)
    assert record["leads"] == ["II"]


def test_parsed_result_feeds_analysis_types(tmp_path) -> None:
    adapter = WfdbImportAdapter()
    source = ImportSource(
        kind="path",
        path=SAMPLES_DIR / "100.hea",
        workspace=tmp_path,
    )
    parsed = adapter.parse(source, ParseParameters())
    signals = parsed.to_ecg_signals()

    assert [signal.lead for signal in signals] == ["MLII", "V5"]
    for signal in signals:
        assert signal.fs == 360.0
        assert signal.samples.dtype == np.float32
        assert signal.n_samples == 650000
    assert signals[0].annotations is not None
    assert len(signals[0].annotations) == len(parsed.reference_annotations or [])


def test_unit_correction_scales_to_mv(tmp_path) -> None:
    adapter = WfdbImportAdapter()
    source = ImportSource(kind="path", path=SAMPLES_DIR / "100.hea", workspace=tmp_path)
    normal = adapter.parse(source, ParseParameters())
    micro = adapter.parse(source, ParseParameters(unit="uV"))
    np.testing.assert_allclose(
        micro.leads[0].samples,
        normal.leads[0].samples * 0.001,
        rtol=0,
        atol=1e-12,
    )


def _write_wfdb(wfdb, *, fs: int, wave: np.ndarray):
    """把合成 500Hz 记录写到 samples 旁边的临时目录（测试专用）。"""
    import tempfile
    from pathlib import Path

    directory = Path(tempfile.mkdtemp(prefix="eh-wfdb-500-"))
    wfdb.wrsamp(
        "synth500",
        fs=fs,
        units=["mV"],
        sig_name=["II"],
        p_signal=wave.reshape(-1, 1),
        fmt=["16"],
        write_dir=str(directory),
    )
    return directory / "synth500.hea"

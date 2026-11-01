"""导出/备份往返、CSV 结构、损坏备份校验。"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from backup_helpers import create_full_record, create_record_with_analysis

from eclipse_health_backend.analysis.ids import rfc3339
from eclipse_health_backend.domain.common import utc_now

ZIP_MEDIA = "application/zip"


def _backup(client, fmt: str):
    return client.get(f"/api/v1/export/backup?format={fmt}")


def _restore(client, data: bytes):
    return client.post(
        "/api/v1/import/backup",
        files={"file": ("backup.zip", data, ZIP_MEDIA)},
    )


def _rebuild_zip(data: bytes, *, rewrite: dict[str, bytes] | None = None, drop=()):
    source = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            if info.filename in drop:
                continue
            payload = source.read(info.filename)
            if rewrite and info.filename in rewrite:
                payload = rewrite[info.filename]
            target.writestr(info, payload)
    return buffer.getvalue()


def test_zip_roundtrip_preserves_signal_and_measurements(client, default_member):
    full = create_full_record(client, default_member["id"])
    old_record = full["record"]
    old_signal = client.get(f"/api/v1/records/{old_record['id']}/signals").json()[0]
    old_detail = client.get(f"/api/v1/analyses/{full['analysisId']}").json()

    response = _backup(client, "zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(ZIP_MEDIA)
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format"] == "eclipse-health-backup"
    assert manifest["version"] == 1
    assert manifest["counts"]["records"] == 1
    assert manifest["counts"]["measurements"] == len(old_detail["measurements"])
    assert "records.json" in names
    assert "signals.json" in names
    assert "measurements.csv" in names
    assert "records.csv" in names
    assert f"signals/{old_signal['id']}.f32" in names
    assert f"analyses/{full['analysisId']}.json" in names
    assert f"reports/{full['reportId']}.png" in names

    injected = archive.read("records.json").decode("utf-8")
    assert old_record["notes"] in injected

    purge = client.delete("/api/v1/privacy/all?confirm=DELETE_ALL")
    assert purge.status_code == 200

    restored = _restore(client, response.content)
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["imported"] == {
        "records": 1,
        "signals": 1,
        "analyses": 1,
        "measurements": len(old_detail["measurements"]),
        "annotations": 0,
        "reports": 1,
    }
    assert body["skipped"]["records"] == 0
    assert body["autoBackup"].startswith("pre-restore-")

    records = client.get("/api/v1/records").json()["items"]
    assert len(records) == 1
    new_record = records[0]
    assert new_record["id"] != old_record["id"]
    assert new_record["notes"] == old_record["notes"]

    new_signal = client.get(f"/api/v1/records/{new_record['id']}/signals").json()[0]
    assert new_signal["id"] != old_signal["id"]
    assert new_signal["storage"]["sha256"] == old_signal["storage"]["sha256"]

    new_analysis_id = client.get(
        f"/api/v1/records/{new_record['id']}/analyses"
    ).json()["items"][0]["id"]
    new_detail = client.get(f"/api/v1/analyses/{new_analysis_id}").json()
    old_values = {item["code"]: item["value"] for item in old_detail["measurements"]}
    new_values = {item["code"]: item["value"] for item in new_detail["measurements"]}
    assert new_values == old_values
    assert len(new_detail["beats"]) == len(old_detail["beats"])

    reports = client.get(f"/api/v1/records/{new_record['id']}/reports").json()["items"]
    assert len(reports) == 1
    download = client.get(f"/api/v1/reports/{reports[0]['reportId']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")


def test_restore_uses_new_ids_without_overwriting(client, default_member):
    record, _ = create_record_with_analysis(client, default_member["id"])
    data = _backup(client, "zip").content
    response = _restore(client, data)
    assert response.status_code == 200
    records = client.get("/api/v1/records").json()["items"]
    assert len(records) == 2
    assert {item["id"] for item in records} != {record["id"]}
    assert record["id"] in {item["id"] for item in records}


def test_json_export_references_signals_instead_of_embedding(client, default_member):
    record, _ = create_record_with_analysis(client, default_member["id"])
    response = _backup(client, "json")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "eclipse-health-backup"
    assert "signalPolicy" in body
    assert len(body["records"]) == 1
    assert len(body["analyses"]) == 1
    assert len(body["measurements"]) == 3
    assert {item["code"] for item in body["measurements"]} == {
        "heart_rate_mean",
        "rmssd",
        "n_ratio",
    }
    signal = body["signals"][0]
    assert signal["recordId"] == record["id"]
    assert len(signal["storage"]["sha256"]) == 64
    assert "samples" not in signal
    assert "data" not in signal
    assert "base64" not in json.dumps(signal)


def test_csv_is_flat_record_measurement_table(client, default_member):
    create_record_with_analysis(client, default_member["id"])
    response = _backup(client, "csv")
    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    lines = text.splitlines()
    header = lines[0].split(",")
    assert header[:3] == ["recordId", "memberId", "recordType"]
    assert "analysisId" in header
    assert "measurementCode" in header
    assert "measurementValue" in header
    assert len(lines) == 1 + 3  # 一条记录 × 三个测量值
    assert "heart_rate_mean" in text
    assert "72.0" in text


def test_backup_file_name_does_not_leak_metadata(client, default_member):
    create_record_with_analysis(
        client, default_member["id"], notes="PHI_NOTE_SHOULD_NOT_APPEAR"
    )
    response = _backup(client, "zip")
    disposition = response.headers["content-disposition"]
    assert "eclipse-health-backup-" in disposition
    assert "PHI_NOTE_SHOULD_NOT_APPEAR" not in disposition
    assert "Synthetic" not in disposition
    assert "Test" not in disposition


def test_corrupted_entries_return_422(client, default_member):
    create_record_with_analysis(client, default_member["id"])
    data = _backup(client, "zip").content
    tampered = _rebuild_zip(
        data, rewrite={"records.json": b'[{"id":"rec_tampered"}]'}
    )
    response = _restore(client, tampered)
    assert response.status_code == 422
    assert response.json()["code"] == "backup_corrupted"


def test_newer_backup_version_is_rejected(client, default_member):
    create_record_with_analysis(client, default_member["id"])
    data = _backup(client, "zip").content
    source = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(source.read("manifest.json"))
    manifest["version"] = 99
    tampered = _rebuild_zip(
        data,
        rewrite={
            "manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        },
    )
    response = _restore(client, tampered)
    assert response.status_code == 422
    assert response.json()["code"] == "backup_incompatible_version"


def test_missing_manifest_is_rejected(client, default_member):
    create_record_with_analysis(client, default_member["id"])
    data = _backup(client, "zip").content
    tampered = _rebuild_zip(data, drop={"manifest.json"})
    response = _restore(client, tampered)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_backup"


def test_truncated_upload_is_rejected(client, default_member):
    create_record_with_analysis(client, default_member["id"])
    data = _backup(client, "zip").content
    response = _restore(client, data[: len(data) // 2])
    assert response.status_code == 422
    assert response.json()["code"] == "backup_corrupted"


@pytest.mark.parametrize("fmt", ["zip", "json", "csv"])
def test_empty_export_is_valid(client, fmt):
    response = _backup(client, fmt)
    assert response.status_code == 200
    assert response.content


def test_empty_zip_restores_zero_counts(client):
    data = _backup(client, "zip").content
    response = _restore(client, data)
    assert response.status_code == 200
    assert response.json()["imported"] == {
        "records": 0,
        "signals": 0,
        "analyses": 0,
        "measurements": 0,
        "annotations": 0,
        "reports": 0,
    }


def test_export_manifest_timestamp_is_rfc3339(client):
    manifest = json.loads(
        zipfile.ZipFile(io.BytesIO(_backup(client, "zip").content)).read("manifest.json")
    )
    assert manifest["createdAt"]
    assert manifest["createdAt"] > rfc3339(utc_now().replace(year=2020))

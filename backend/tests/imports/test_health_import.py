"""Apple Health / 小米运动直接导入：计数、单位、去重、错误码。"""

from __future__ import annotations

import io
import sys
import zipfile

import pytest
from import_helpers import API, BACKEND_ROOT, commit, read_signal, upload_preview

FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "imports"
sys.path.insert(0, str(FIXTURES / "apple-health"))
sys.path.insert(0, str(FIXTURES / "xiaomi"))

import export_builder
import fitness_builder

APPLE_COUNTS = {
    "steps": 2,
    "heartRate": 2,
    "sleep": 1,
    "bodyMass": 1,
    "bloodPressure": 1,
    "ecg": 1,
}
XIAOMI_COUNTS = {"steps": 2, "heartRate": 2, "sleep": 1, "bodyMass": 1}


def _preview(client, name: str, payload: bytes, **form) -> dict:
    response = upload_preview(client, name, payload, **form)
    assert response.status_code == 200, response.text
    return response.json()


def _health_records(client, record_type: str) -> list[dict]:
    response = client.get(f"{API}/records", params={"recordType": record_type})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _apple_zip_bytes(**kwargs) -> bytes:
    return export_builder.apple_zip(
        xml=kwargs.get("xml", export_builder.export_xml()),
        ecg_files=kwargs.get(
            "ecg_files",
            {"ecg-2026-10-28.csv": export_builder.ecg_csv(recorded_at=export_builder.ECG_START)},
        ),
        prefix=kwargs.get("prefix", "apple_health_export/"),
    )


def _zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_apple_zip_preview_and_commit(client, default_member: dict) -> None:
    preview = _preview(client, "export.zip", _apple_zip_bytes())

    assert preview["format"] == "apple-health"
    assert preview["adapterId"] == "org.eclipsehealth.apple-health"
    assert preview["recordCounts"] == APPLE_COUNTS
    assert preview["totalRecords"] == 8
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    assert preview["samplingRate"] == pytest.approx(512.0)
    assert preview["leads"] == ["I"]
    assert len(preview["preview"]["samples"]) == 1024

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 8
    assert body["skipped"] == 0
    assert body["failed"] == 0
    assert body["duplicateFile"] is False
    assert body["recordCounts"] == APPLE_COUNTS
    assert body["recordId"]

    steps = _health_records(client, "org.eclipsehealth.health.steps")
    assert len(steps) == 2
    assert {item["payload"]["value"] for item in steps} == {1000, 1500}
    assert all(item["payload"]["unit"] == "count" for item in steps)
    assert all(item["metadata"]["importSource"] == "apple-health" for item in steps)
    assert all(item["metadata"]["externalId"].startswith("apple:") for item in steps)
    assert all(item["source"]["kind"] == "import" for item in steps)

    heart = _health_records(client, "org.eclipsehealth.health.heart-rate")
    assert {item["payload"]["value"] for item in heart} == {72, 75}
    assert all(item["unit"] == "count/min" for item in heart)

    mass = _health_records(client, "org.eclipsehealth.health.body-mass")
    assert mass[0]["payload"]["value"] == pytest.approx(70.5)
    assert mass[0]["unit"] == "kg"

    sleep = _health_records(client, "org.eclipsehealth.health.sleep")
    assert sleep[0]["payload"]["value"] == "asleep-core"
    assert sleep[0]["durationSec"] == pytest.approx(7200.0)

    pressure = _health_records(client, "org.eclipsehealth.health.blood-pressure")
    assert pressure[0]["payload"]["value"] == {"systolic": 120, "diastolic": 80}
    assert pressure[0]["unit"] == "mm[Hg]"

    ecg = _health_records(client, "org.eclipsehealth.ecg")
    assert len(ecg) == 1
    assert ecg[0]["metadata"]["importSource"] == "apple-health"
    samples = read_signal(client, ecg[0]["id"], "I")
    assert samples.size == 1024
    assert samples[0] == pytest.approx(-0.32, abs=1e-6)
    assert samples[1] == pytest.approx(-0.31, abs=1e-6)


def test_apple_reimport_skips_duplicate_file(client, default_member: dict) -> None:
    payload = _apple_zip_bytes()
    first = _preview(client, "export.zip", payload)
    assert commit(client, first["importId"], default_member["id"]).status_code == 201

    second = _preview(client, "export.zip", payload)
    response = commit(client, second["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["duplicateFile"] is True
    assert body["created"] == 0
    assert body["skipped"] == 8
    assert body["recordId"] == ""
    assert body["record"] is None


def test_apple_xml_only_imports_health_records(client, default_member: dict) -> None:
    preview = _preview(client, "export.xml", export_builder.export_xml().encode("utf-8"))
    assert preview["format"] == "apple-health"
    assert preview["recordCounts"].get("ecg", 0) == 0
    assert preview["totalRecords"] == 7

    body = commit(client, preview["importId"], default_member["id"]).json()
    assert body["created"] == 7
    assert "ecg" not in body["recordCounts"]


def test_apple_zip_missing_export_xml_reports_clear_error(client) -> None:
    archive = export_builder.apple_zip(
        xml=None,
        ecg_files={"ecg.csv": export_builder.ecg_csv()},
    )
    response = upload_preview(client, "apple_health_export.zip", archive)
    assert response.status_code == 422
    assert response.json()["code"] == "apple_export_missing"


def test_apple_bad_ecg_csv_reports_clear_error(client) -> None:
    bad = "time,voltage\nabc,def\nghi,jkl\n"
    archive = export_builder.apple_zip(
        xml=export_builder.export_xml(),
        ecg_files={"ecg.csv": bad},
    )
    response = upload_preview(client, "export.zip", archive)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_ecg_csv"


def test_apple_invalid_xml_reports_clear_error(client) -> None:
    response = upload_preview(
        client, "export.xml", b'<?xml version="1.0"?><HealthData><Record'
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_apple_export"


def test_apple_blood_pressure_kpa_is_converted(client, default_member: dict) -> None:
    xml = export_builder.export_xml(include_sleep=False, include_ignored=False).replace(
        export_builder.correlation(),
        export_builder.correlation(systolic="16", diastolic="10.7", unit="kPa"),
    )
    preview = _preview(client, "export.xml", xml.encode("utf-8"))
    commit(client, preview["importId"], default_member["id"])
    pressure = _health_records(client, "org.eclipsehealth.health.blood-pressure")
    assert pressure[0]["payload"]["value"]["systolic"] == pytest.approx(120.01, abs=0.01)
    assert pressure[0]["payload"]["value"]["diastolic"] == pytest.approx(80.26, abs=0.01)


def test_xiaomi_csv_preview_and_commit(client, default_member: dict) -> None:
    payload = fitness_builder.fitness_csv().encode("utf-8")
    preview = _preview(client, "hlth_center_fitness_data.csv", payload)

    assert preview["format"] == "xiaomi"
    assert preview["adapterId"] == "org.eclipsehealth.xiaomi"
    assert preview["recordCounts"] == XIAOMI_COUNTS
    assert preview["totalRecords"] == 6
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 6
    assert body["recordCounts"] == XIAOMI_COUNTS

    steps = _health_records(client, "org.eclipsehealth.health.steps")
    assert {item["payload"]["value"] for item in steps} == {1000, 1200}
    assert all(item["metadata"]["importSource"] == "xiaomi-mi-fitness" for item in steps)

    sleep = _health_records(client, "org.eclipsehealth.health.sleep")
    assert sleep[0]["payload"]["value"] == "deep"
    assert sleep[0]["durationSec"] == pytest.approx(7200.0)

    weight = _health_records(client, "org.eclipsehealth.health.body-mass")
    assert weight[0]["payload"]["value"] == pytest.approx(70.5)


def test_xiaomi_reimport_skips_duplicate_file(client, default_member: dict) -> None:
    payload = fitness_builder.fitness_csv().encode("utf-8")
    first = _preview(client, "hlth_center_fitness_data.csv", payload)
    commit(client, first["importId"], default_member["id"])

    second = _preview(client, "hlth_center_fitness_data.csv", payload)
    body = commit(client, second["importId"], default_member["id"]).json()
    assert body["created"] == 0
    assert body["skipped"] == 6
    assert body["duplicateFile"] is True


def test_xiaomi_unknown_columns_reports_clear_error(client) -> None:
    payload = "date,metric,reading\n2026-10-28,steps,100\n"
    response = upload_preview(client, "hlth_center_fitness_data.csv", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_xiaomi_export"


def test_xiaomi_encrypted_zip_reports_clear_error(client) -> None:
    raw = bytearray(
        _zip_with({"hlth_center_fitness_data.csv": fitness_builder.fitness_csv().encode("utf-8")})
    )
    # 置位「加密」标志：local header +6，central directory header +8。
    index = 0
    while True:
        local = raw.find(b"PK\x03\x04", index)
        if local < 0:
            break
        raw[local + 6] |= 0x01
        index = local + 4
    index = 0
    while True:
        central = raw.find(b"PK\x01\x02", index)
        if central < 0:
            break
        raw[central + 8] |= 0x01
        index = central + 4

    response = upload_preview(client, "xiaomi_fitness.zip", bytes(raw))
    assert response.status_code == 422
    assert response.json()["code"] == "encrypted_export"


def test_health_adapters_are_registered() -> None:
    from eclipse_health_backend.importers.registry import build_default_registry

    registry = build_default_registry()
    for fmt in ("apple-health", "xiaomi"):
        adapter = registry.find(fmt)
        assert adapter is not None, fmt
        assert adapter.supported is True
        assert adapter.adapter_id.startswith("org.eclipsehealth.")

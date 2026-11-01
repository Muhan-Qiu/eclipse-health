"""io.github.dogsheep.healthkit-to-sqlite · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "healthkit-to-sqlite"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))

XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min"
          startDate="2026-10-31 08:00:00 +0800" endDate="2026-10-31 08:00:05 +0800" value="72"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count"
          startDate="2026-10-31 09:00:00 +0800" endDate="2026-10-31 10:00:00 +0800" value="1200"/>
  <Workout workoutActivityType="HKWorkoutActivityTypeRunning"
           startDate="2026-10-31 18:00:00 +0800" endDate="2026-10-31 18:30:00 +0800"
           duration="30" totalEnergyBurned="300" totalDistance="5.2"/>
</HealthData>
"""


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_healthkit_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.dogsheep.healthkit-to-sqlite"
    assert manifest.type.value == "data-source"
    assert manifest.dependencies == ()


def test_parse_record_maps_metric_and_drops_device_name() -> None:
    item = ADAPTER.parse_record(
        {
            "type": "HKQuantityTypeIdentifierHeartRate",
            "sourceName": "Watch",
            "unit": "count/min",
            "startDate": "2026-10-31 08:00:00",
            "value": "72",
        }
    )
    assert item["recordType"] == "vital.measurement"
    assert item["payload"]["metric"] == "heart_rate"
    assert item["payload"]["value"] == 72.0
    assert "sourceName" not in item["payload"]


def test_parse_record_rejects_missing_type() -> None:
    with pytest.raises(ADAPTER.HealthExportError):
        ADAPTER.parse_record({"startDate": "2026-10-31"})


def test_read_export_xml_counts(tmp_path: Path) -> None:
    target = tmp_path / "export.xml"
    target.write_text(XML, encoding="utf-8")
    parsed = ADAPTER.read_export(target)
    assert parsed["count"] == 3
    assert parsed["truncated"] is False
    assert parsed["counts"] == {"activity.sample": 1, "activity.workout": 1, "vital.measurement": 1}


def test_read_export_zip_and_limit(tmp_path: Path) -> None:
    target = tmp_path / "export.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("apple_health_export/export.xml", XML)
    parsed = ADAPTER.read_export(target, limit=2)
    assert parsed["count"] == 2
    assert parsed["truncated"] is True


def test_read_export_invalid_file(tmp_path: Path) -> None:
    target = tmp_path / "broken.xml"
    target.write_text("<HealthData><Record", encoding="utf-8")
    with pytest.raises(ADAPTER.HealthExportError) as info:
        ADAPTER.read_export(target)
    assert info.value.code == "invalid_xml"


def test_handle_import_success(tmp_path: Path) -> None:
    target = tmp_path / "export.xml"
    target.write_text(XML, encoding="utf-8")
    result = MAIN.handle("import.healthkit", {"path": str(target)})
    assert result["summary"]["count"] == 3
    assert result["disclaimer"].startswith("非医疗器械")


def test_handle_import_missing_path() -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("import.healthkit", {})
    assert info.value.data["code"] == "INVALID_INPUT"

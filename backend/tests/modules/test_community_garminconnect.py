"""io.github.cyberjunky.garminconnect · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "garminconnect"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_garminconnect_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.cyberjunky.garminconnect"
    assert "network" in manifest.permissions
    assert "connect.garmin.com" in manifest.allowed_hosts


def test_normalize_activity() -> None:
    item = ADAPTER.normalize_activity(
        {
            "activityId": 42,
            "activityName": "Morning run",
            "startTimeLocal": "2026-10-31 07:00:00",
            "activityType": {"typeKey": "running"},
            "distance": 5200.0,
            "duration": 1800.0,
            "averageHR": 145,
            "calories": 320,
        }
    )
    assert item["activityType"] == "running"
    assert item["distanceMeters"] == 5200.0
    assert item["averageHeartRate"] == 145.0


def test_normalize_activity_rejects_missing_id() -> None:
    with pytest.raises(ADAPTER.GarminAdapterError):
        ADAPTER.normalize_activity({"activityName": "x"})


def test_normalize_sleep_dto() -> None:
    item = ADAPTER.normalize_sleep(
        {
            "dailySleepDTO": {
                "sleepTimeSeconds": 25000,
                "deepSleepSeconds": 6000,
                "calendarDate": "2026-10-31",
            }
        }
    )
    assert item["totalSleepSeconds"] == 25000.0
    assert item["deepSleepSeconds"] == 6000.0
    assert item["start"] == "2026-10-31"


def test_normalize_body_converts_grams() -> None:
    item = ADAPTER.normalize_body(
        {"startDate": "2026-10-31", "totalAverage": {"weight": 60000, "bmi": 22.5, "bodyFat": 18.0}}
    )
    assert item["weightKg"] == 60.0
    assert item["bmi"] == 22.5


def test_build_login_rejects_missing_password() -> None:
    with pytest.raises(ADAPTER.GarminAdapterError) as info:
        ADAPTER.build_login({"email": "a@example.com"})
    assert info.value.code == "invalid_input"


def test_handle_import_missing_credentials() -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("import.garmin", {"email": "a@example.com"})
    assert info.value.code == -32602


def test_import_without_upstream_is_reported() -> None:
    if importlib.util.find_spec("garminconnect") is not None:
        pytest.skip("garminconnect installed; live login is intentionally not tested")
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("import.garmin", {"email": "a@example.com", "password": "x"})
    assert info.value.data["code"] == "upstream_unavailable"

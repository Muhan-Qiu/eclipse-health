"""Stravalib 官方模块：manifest、adapter 纯函数与 RPC 分发测试（不需要上游库）。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "stravalib"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_stravalib_adapter", "adapter.py")
MAIN = _load("official_stravalib_main", "main.py")

SAMPLE = {
    "id": 12345,
    "name": "Morning ride",
    "sport_type": "Ride",
    "start_date": "2026-11-01T07:30:00Z",
    "distance": 12500.0,
    "moving_time": 1800,
    "average_heartrate": 132.5,
    "max_heartrate": 168,
}


def test_manifest_is_valid_and_declares_network_and_dependency() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.stravalib.stravalib"
    assert data["type"] == "data-source"
    assert data["allowedHosts"] == ["www.strava.com"]
    assert data["dependencies"] == ["stravalib>=2.0,<3"]
    assert data["contributes"]["sources"][0]["id"] == "strava"


def test_normalize_activity_success() -> None:
    item = ADAPTER.normalize_activity(SAMPLE)
    assert item["id"] == "12345"
    assert item["sport"] == "Ride"
    assert item["distanceKm"] == 12.5
    assert item["movingTimeS"] == 1800
    assert item["avgHeartRate"] == 132.5
    assert item["startDate"].startswith("2026-11-01T07:30:00")


def test_normalize_rejects_missing_id() -> None:
    broken = dict(SAMPLE)
    broken.pop("id")
    with pytest.raises(ValueError, match="id"):
        ADAPTER.normalize_activity(broken)


def test_weekly_summary_groups_iso_weeks() -> None:
    second = dict(SAMPLE, id=12346, start_date="2026-10-20T08:00:00Z", distance=5000.0)
    result = ADAPTER.weekly_summary([SAMPLE, second])
    assert result["activityCount"] == 2
    assert len(result["weeks"]) == 2
    assert result["totalDistanceKm"] == 17.5
    total_hours = sum(item["movingHours"] for item in result["weeks"])
    assert total_hours == 1.0
    assert result["disclaimer"]


def test_rpc_success_and_error_paths() -> None:
    health = MAIN.handle("health", {})
    assert health["ok"] is True
    assert isinstance(health["dependencyAvailable"], bool)
    result = MAIN.handle("activities.normalize", {"activities": [SAMPLE]})
    assert result["count"] == 1
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("activities.normalize", {"activities": "nope"})
    assert info.value.data["code"] == "INVALID_INPUT"
    with pytest.raises(MAIN.RpcError) as missing:
        MAIN.handle("strava.fetch", {})
    assert missing.value.code == -32602

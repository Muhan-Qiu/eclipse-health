"""Dexcom CGM 模块：manifest、单位/趋势映射与 worker 参数校验。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "pydexcom"


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_pydexcom_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adapter() -> ModuleType:
    return _load("adapter")


@pytest.fixture(scope="module")
def worker() -> ModuleType:
    return _load("main")


def test_manifest_matches_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["id"] == "io.github.gagebenne.pydexcom"
    assert manifest["permissions"] == ["network", "records:write"]
    assert manifest["allowedHosts"] == ["share2.dexcom.com", "shareous1.dexcom.com"]


def test_normalize_mgdl_reading(adapter: ModuleType) -> None:
    reading = adapter.normalize_reading(
        {"value": 120, "trend": 4, "timestamp": "2026-01-01T10:00:00Z"}
    )
    assert reading["valueMgdl"] == 120.0
    assert reading["valueMmol"] == 6.7
    assert reading["trendText"] == "flat"
    assert reading["measuredAt"] == "2026-01-01T10:00:00Z"


def test_normalize_mmol_reading(adapter: ModuleType) -> None:
    reading = adapter.normalize_reading({"mmol_l": 5.5, "trend_direction": "singleUp"})
    assert 98 <= reading["valueMgdl"] <= 100
    assert reading["trendText"] == "singleUp"


def test_normalize_rejects_bad_values(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.normalize_reading({})
    with pytest.raises(ValueError):
        adapter.normalize_reading({"value": 0})
    with pytest.raises(TypeError):
        adapter.normalize_reading("120")  # type: ignore[arg-type]


def test_summarize_readings(adapter: ModuleType) -> None:
    readings = [
        adapter.normalize_reading({"value": 60, "timestamp": "2026-01-01T09:00:00Z"}),
        adapter.normalize_reading({"value": 120, "timestamp": "2026-01-01T10:00:00Z"}),
        adapter.normalize_reading({"value": 250, "timestamp": "2026-01-01T11:00:00Z"}),
    ]
    summary = adapter.summarize_readings(readings)
    assert summary["samples"] == 3
    assert summary["avgMgdl"] == 143.3
    assert summary["timeInRangePercent"] == 33.3
    assert summary["lowCount"] == 1
    assert summary["highCount"] == 1
    assert summary["latest"]["valueMgdl"] == 250.0


def test_summarize_empty_is_error(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.summarize_readings([])


def test_worker_latest_before_readings(worker: ModuleType) -> None:
    latest = worker.handle("latestReading", {})
    assert latest["available"] is False
    assert latest["valueMgdl"] == 0


def test_worker_readings_requires_credentials(worker: ModuleType) -> None:
    with pytest.raises(worker.RpcError) as info:
        worker.handle("readings", {"username": "u"})
    assert info.value.data["code"] == "INVALID_INPUT"
    with pytest.raises(worker.RpcError):
        worker.handle("readings", {"username": "u", "password": "p", "region": "xx"})


def test_worker_initialize_and_health(worker: ModuleType) -> None:
    assert worker.handle("initialize", {})["moduleId"] == "io.github.gagebenne.pydexcom"
    health = worker.handle("health", {})
    assert health["requiresNetwork"] is True
    assert "pydexcomAvailable" in health

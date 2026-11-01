"""FIT Parser 模块：manifest、半圆转换、摘要与 worker 错误路径。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "fitparse"


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_fitparse_{name}", path)
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
    assert manifest["id"] == "io.github.dtcooper.fitparse"
    assert manifest["dependencies"] == ["fitparse>=1.2,<2"]


def test_semicircles_to_degrees(adapter: ModuleType) -> None:
    assert adapter.semicircles_to_degrees(0) == 0
    assert adapter.semicircles_to_degrees(90.0) == 90.0
    assert adapter.semicircles_to_degrees(2**30) == 90.0
    assert adapter.semicircles_to_degrees("bad") is None


def test_record_from_fitparse(adapter: ModuleType) -> None:
    record = adapter.record_from_fitparse(
        {
            "timestamp": "2026-01-01T10:00:00+00:00",
            "heart_rate": 130,
            "enhanced_speed": 2.5,
            "distance": 900.0,
            "position_lat": 2**30,
            "position_long": -2**30,
        }
    )
    assert record["heartRate"] == 130
    assert record["latitude"] == 90.0
    assert record["longitude"] == -90.0


def test_record_rejects_non_dict(adapter: ModuleType) -> None:
    with pytest.raises(TypeError):
        adapter.record_from_fitparse([])  # type: ignore[arg-type]


def test_summarize_and_payload(adapter: ModuleType) -> None:
    records = [
        adapter.record_from_fitparse(
            {"timestamp": "2026-01-01T10:00:00Z", "heart_rate": 100, "distance": 0}
        ),
        adapter.record_from_fitparse(
            {"timestamp": "2026-01-01T10:05:00Z", "heart_rate": 160, "distance": 2000}
        ),
    ]
    summary = adapter.summarize_records(records)
    assert summary["durationSeconds"] == 300
    assert summary["distanceKm"] == 2.0
    assert summary["maxHeartRate"] == 160
    payload = adapter.session_payload(summary, [{"id": 1}])
    assert payload["source"] == "fitparse"
    assert payload["laps"] == [{"id": 1}]


def test_summarize_empty_is_error(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.summarize_records([])


def test_worker_initialize_and_missing_path(worker: ModuleType) -> None:
    assert worker.handle("initialize", {})["moduleId"] == "io.github.dtcooper.fitparse"
    with pytest.raises(worker.RpcError) as info:
        worker.handle("importFile", {"path": str(MODULE_DIR / "missing.fit")})
    assert info.value.data["code"] == "INVALID_INPUT"

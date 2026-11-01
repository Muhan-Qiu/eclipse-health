"""FIT Decoder 模块：manifest、纯函数映射与 worker 错误路径。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "fitdecode"


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_fitdecode_{name}", path)
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
    assert manifest["id"] == "io.github.polyvertex.fitdecode"
    assert manifest["version"] == "0.1.0"
    assert manifest["dependencies"] == ["fitdecode>=0.10,<1"]


def test_normalize_record(adapter: ModuleType) -> None:
    record = adapter.normalize_fit_record(
        {
            "timestamp": "2026-01-01T10:00:00+00:00",
            "heart_rate": 140,
            "enhanced_speed": 3.5,
            "distance": 1200.0,
            "enhanced_altitude": 45.0,
        }
    )
    assert record["heartRate"] == 140
    assert record["speedMps"] == 3.5
    assert record["distanceM"] == 1200.0
    assert record["timestamp"].startswith("2026-01-01")


def test_normalize_rejects_bad_heart_rate(adapter: ModuleType) -> None:
    assert adapter.normalize_fit_record({"heart_rate": 999})["heartRate"] is None
    assert adapter.normalize_fit_record({"heart_rate": -5})["heartRate"] is None


def test_summarize_records(adapter: ModuleType) -> None:
    records = [
        adapter.normalize_fit_record(
            {"timestamp": "2026-01-01T10:00:00+00:00", "heart_rate": 120, "distance": 0}
        ),
        adapter.normalize_fit_record(
            {"timestamp": "2026-01-01T10:10:00+00:00", "heart_rate": 150, "distance": 3000}
        ),
    ]
    summary = adapter.summarize_records(records)
    assert summary["durationSeconds"] == 600
    assert summary["distanceKm"] == 3.0
    assert summary["avgHeartRate"] == 135.0
    assert summary["maxHeartRate"] == 150
    assert summary["quality"] == "good"
    assert "非医疗器械" in summary["nonDiagnostic"]


def test_summarize_empty_is_error(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.summarize_records([])


def test_session_payload(adapter: ModuleType) -> None:
    payload = adapter.session_payload({"startedAt": "x", "durationSeconds": 1.5})
    assert payload["startedAt"] == "x"
    assert payload["durationSeconds"] == 1.5
    assert payload["source"] == "fit"


def test_worker_initialize_and_health(worker: ModuleType) -> None:
    init = worker.handle("initialize", {})
    assert init["moduleId"] == "io.github.polyvertex.fitdecode"
    health = worker.handle("health", {})
    assert health["ok"] is True
    assert "fitdecodeAvailable" in health


def test_worker_summary_rejects_missing_path(worker: ModuleType) -> None:
    with pytest.raises(worker.RpcError) as info:
        worker.handle("summary", {})
    assert info.value.data["code"] == "INVALID_INPUT"

"""BLE Health 模块：manifest、GATT 字节解析与离线回放主路径。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "bleak"


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_bleak_{name}", path)
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
    assert manifest["id"] == "io.github.hbldh.bleak"
    assert manifest["dependencies"] == ["bleak>=0.22,<2"]


def test_heart_rate_uint8(adapter: ModuleType) -> None:
    parsed = adapter.parse_heart_rate_measurement(bytes([0x00, 72]))
    assert parsed["heartRate"] == 72
    assert parsed["sensorContact"] is None


def test_heart_rate_uint16_and_rr(adapter: ModuleType) -> None:
    parsed = adapter.parse_heart_rate_measurement(bytes([0x16, 60, 0x00, 0x04]))
    assert parsed["heartRate"] == 60
    assert parsed["sensorContact"] is True
    assert parsed["rrIntervalsMs"] == [1000.0]


def test_heart_rate_rejects_bad_data(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.parse_heart_rate_measurement(bytes([0x00]))
    with pytest.raises(ValueError):
        adapter.parse_heart_rate_measurement(bytes([0x00, 0]))
    with pytest.raises(TypeError):
        adapter.parse_heart_rate_measurement("not-bytes")


def test_body_composition(adapter: ModuleType) -> None:
    # flags=0x0400（SI + weight），体脂 200 → 20.0%，体重 14000 → 70 kg。
    parsed = adapter.parse_body_composition_measurement(
        bytes([0x00, 0x04, 0xC8, 0x00, 0xB0, 0x36])
    )
    assert parsed["bodyFatPercent"] == 20.0
    assert parsed["weightKg"] == 70.0
    assert parsed["measuredAt"] is None


def test_summarize_hr_samples(adapter: ModuleType) -> None:
    summary = adapter.summarize_hr_samples(
        [{"heartRate": 60}, {"heartRate": 90}, {"heartRate": None}]
    )
    assert summary["avgHeartRate"] == 75.0
    assert summary["minHeartRate"] == 60
    assert summary["coverage"] == 0.667
    assert summary["quality"] == "partial"


def test_summarize_empty_is_error(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.summarize_hr_samples([])


def test_worker_parse_capture(worker: ModuleType) -> None:
    sample = worker.handle("parseCapture", {"kind": "heartRate", "dataHex": "0048"})
    assert sample["heartRate"] == 72
    latest = worker.handle("latestSample", {})
    assert latest["available"] is True
    assert latest["heartRate"] == 72


def test_worker_parse_capture_errors(worker: ModuleType) -> None:
    with pytest.raises(worker.RpcError) as info:
        worker.handle("parseCapture", {"kind": "unknown", "dataHex": "0048"})
    assert info.value.data["code"] == "INVALID_INPUT"
    with pytest.raises(worker.RpcError):
        worker.handle("parseCapture", {"kind": "heartRate", "dataHex": "zz"})


def test_worker_read_requires_address(worker: ModuleType) -> None:
    with pytest.raises(worker.RpcError) as info:
        worker.handle("readHeartRate", {})
    assert info.value.data["code"] == "INVALID_INPUT"

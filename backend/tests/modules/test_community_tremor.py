"""Tremor 官方模块：manifest、adapter 纯函数与 RPC 分发测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "tremor"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_tremor_adapter", "adapter.py")
MAIN = _load("official_tremor_main", "main.py")


def test_manifest_is_valid() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.tremorlabs.tremor"
    assert data["contributes"]["ui"]["widgets"][0]["view"]["type"] == "stat"


def test_kpis_success_computes_delta_and_progress() -> None:
    result = ADAPTER.build_kpis(
        [{"label": "静息心率", "value": 60, "previous": 64, "unit": "bpm", "min": 40, "max": 100}]
    )
    card = result["headline"]
    assert result["count"] == 1
    assert card["delta"] == -4.0
    assert card["deltaPercent"] == -6.25
    assert card["direction"] == "down"
    assert card["progress"] == {"min": 40.0, "max": 100.0, "ratio": 0.3333}
    assert result["disclaimer"]


def test_kpis_empty_is_safe() -> None:
    result = ADAPTER.build_kpis([])
    assert result["cards"] == []
    assert result["headline"] is None


def test_kpis_rejects_missing_value() -> None:
    with pytest.raises(ValueError, match="value"):
        ADAPTER.build_kpis([{"label": "x"}])


def test_rpc_success_and_error_path() -> None:
    assert MAIN.handle("health", {})["ok"] is True
    result = MAIN.handle("kpis", {"metrics": [{"label": "步数", "value": 1000}]})
    assert result["count"] == 1
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("kpis", {"metrics": [{"label": "x", "value": "high"}]})
    assert info.value.data["code"] == "INVALID_INPUT"

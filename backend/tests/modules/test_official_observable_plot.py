"""Observable Plot 官方模块：manifest、adapter 纯函数与 RPC 分发测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "observable-plot"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_observable_plot_adapter", "adapter.py")
MAIN = _load("official_observable_plot_main", "main.py")


def test_manifest_is_valid() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.observablehq.plot"
    assert data["contributes"]["ui"]["widgets"]


def test_trend_success_with_pairs() -> None:
    result = ADAPTER.trend([[1, 10], [2, 12]], unit="ms")
    assert result["values"] == [10.0, 12.0]
    assert result["latest"] == {"x": 2, "value": 12.0}
    assert result["unit"] == "ms"
    assert result["disclaimer"]


def test_summary_quantiles() -> None:
    result = ADAPTER.summary([1, 2, 3, 4])
    assert result["count"] == 4
    assert result["median"] == 2.5
    assert result["q1"] == 1.75
    assert result["q3"] == 3.25


def test_summary_empty_is_safe() -> None:
    result = ADAPTER.summary([])
    assert result["count"] == 0
    assert result["median"] is None


def test_histogram_rejects_non_list() -> None:
    with pytest.raises(TypeError, match="数组"):
        ADAPTER.histogram("nope")


def test_rpc_returns_and_raises() -> None:
    assert MAIN.handle("health", {})["ok"] is True
    result = MAIN.handle("plot.histogram", {"values": [1, 2, 3], "bins": 2})
    assert result["count"] == 3
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("plot.summary", {"values": [1, "x"]})
    assert info.value.code == -32602
    assert info.value.data["code"] == "INVALID_INPUT"

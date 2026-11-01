"""ECharts 官方模块：manifest、adapter 纯函数与 RPC 分发测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "echarts"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_echarts_adapter", "adapter.py")
MAIN = _load("official_echarts_main", "main.py")


def test_manifest_is_valid() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.apache.echarts"
    assert data["contributes"]["ui"]["pages"]


def test_line_spec_success() -> None:
    spec = ADAPTER.build_line_spec(
        [{"x": 1, "value": 60}, {"x": 2, "value": 70}],
        label="心率",
        unit="bpm",
    )
    assert spec["kind"] == "line"
    assert spec["labels"] == [1, 2]
    assert spec["series"][0]["data"] == [60.0, 70.0]
    assert spec["latest"] == {"x": 2, "value": 70.0}
    assert spec["disclaimer"]


def test_bar_spec_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="长度不一致"):
        ADAPTER.build_bar_spec(["a", "b"], [1])


def test_distribution_empty_and_constant() -> None:
    empty = ADAPTER.distribution([])
    assert empty["items"] == [] and empty["count"] == 0
    constant = ADAPTER.distribution([5, 5, 5], bins=4)
    assert constant["items"][0]["count"] == 3


def test_distribution_rejects_bad_bins() -> None:
    with pytest.raises(ValueError):
        ADAPTER.distribution([1, 2], bins=0)


def test_rpc_success_and_error_path() -> None:
    health = MAIN.handle("health", {})
    assert health["ok"] is True
    result = MAIN.handle("chart.distribution", {"values": [1, 2, 3], "bins": 2})
    assert result["count"] == 3
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("chart.bar", {"categories": ["a"], "values": [1, 2]})
    assert info.value.data["code"] == "INVALID_INPUT"

"""uPlot 官方模块：manifest、adapter 纯函数与 RPC 分发测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "uplot"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_uplot_adapter", "adapter.py")
MAIN = _load("official_uplot_main", "main.py")


def _manifest() -> dict:
    return json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def test_manifest_is_valid() -> None:
    data = _manifest()
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.leeoniya.uplot"
    assert data["type"] == "dashboard-widget"
    widgets = data["contributes"]["ui"]["widgets"]
    assert widgets and all(item["view"]["type"] in {"stat", "sparkline", "list", "progress", "text"} for item in widgets)


def test_trend_success_sorts_dedupes_and_downsamples() -> None:
    result = ADAPTER.normalize_series(
        [{"t": 3, "v": 2}, {"t": 1, "v": 1}, {"t": 1, "v": 5}],
        unit="bpm",
        max_points=10,
    )
    assert result["points"] == [{"t": 1.0, "v": 5.0}, {"t": 3.0, "v": 2.0}]
    assert result["latest"] == {"t": 3.0, "value": 2.0}
    assert result["unit"] == "bpm"
    assert result["disclaimer"]


def test_trend_empty_is_safe() -> None:
    result = ADAPTER.normalize_series([], unit="bpm")
    assert result["count"] == 0
    assert result["latest"] is None
    assert result["min"] is None


def test_trend_downsample_keeps_endpoints() -> None:
    points = [{"t": index, "v": index} for index in range(100)]
    sampled = ADAPTER.downsample(points, 10)
    assert len(sampled) == 10
    assert sampled[0] == points[0]
    assert sampled[-1] == points[-1]


def test_trend_rejects_non_numeric_value() -> None:
    with pytest.raises(TypeError, match="v 必须是数字"):
        ADAPTER.normalize_series([{"t": 1, "v": "x"}])


def test_rpc_health_initialize_and_error_path() -> None:
    assert MAIN.handle("health", {})["ok"] is True
    capabilities = MAIN.handle("initialize", {"apiVersion": "1.0"})
    assert "trend" in capabilities["capabilities"]
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("trend", {"points": [{"t": 1, "v": "x"}]})
    assert info.value.code == -32602
    assert info.value.data["code"] == "INVALID_INPUT"
    with pytest.raises(MAIN.RpcError):
        MAIN.handle("unknown.method", {})

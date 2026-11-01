"""Activity Calendar 官方模块：manifest、adapter 纯函数与 RPC 分发测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "activity-calendar"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / "src" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("adapter", None)
    spec.loader.exec_module(module)
    return module


ADAPTER = _load("official_activity_calendar_adapter", "adapter.py")
MAIN = _load("official_activity_calendar_main", "main.py")


def test_manifest_is_valid() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    assert data["id"] == "io.github.grubersjoe.activity-calendar"
    assert data["contributes"]["ui"]["pages"]


def test_heatmap_levels_and_streaks() -> None:
    result = ADAPTER.build_heatmap(
        {"2026-10-31": 1, "2026-11-01": 4},
        days=7,
        today=date(2026, 11, 1),
    )
    assert result["startDate"] == "2026-10-26"
    assert result["endDate"] == "2026-11-01"
    assert result["activeDays"] == 2
    assert result["totalCount"] == 5
    assert result["maxDayCount"] == 4
    assert result["longestStreak"] == 2
    assert result["currentStreak"] == 2
    assert result["days"][-1] == {"date": "2026-11-01", "count": 4, "level": 4}
    assert result["days"][-2]["level"] == 1
    assert result["recent"][0]["date"] == "2026-11-01"
    assert result["disclaimer"]


def test_heatmap_empty_is_safe() -> None:
    result = ADAPTER.build_heatmap({}, days=30, today="2026-11-01")
    assert result["activeDays"] == 0
    assert result["totalCount"] == 0
    assert result["currentStreak"] == 0
    assert len(result["days"]) == 30


def test_heatmap_rejects_bad_date_and_negative_count() -> None:
    with pytest.raises(ValueError, match="日期"):
        ADAPTER.build_heatmap({"2026-13-01": 1}, days=7, today="2026-11-01")
    with pytest.raises(ValueError, match="不能为负"):
        ADAPTER.build_heatmap({"2026-11-01": -1}, days=7, today="2026-11-01")


def test_rpc_success_and_error_path() -> None:
    assert MAIN.handle("health", {})["ok"] is True
    result = MAIN.handle("summary", {"counts": {}, "days": 7, "today": "2026-11-01"})
    assert result["activeDays"] == 0
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("heatmap", {"counts": "not-a-map", "days": 7})
    assert info.value.code == -32602
    assert info.value.data["code"] == "INVALID_INPUT"

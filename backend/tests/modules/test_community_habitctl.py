"""io.github.blinry.habitctl · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "habitctl"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_habitctl_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.blinry.habitctl"
    assert manifest.type.value == "health-domain"
    assert manifest.dependencies == ()


def test_parse_habit_list_success() -> None:
    text = "[x] exercise streak=12\n[ ] read\n✔ meditate streak: 3\n"
    habits = ADAPTER.parse_habit_list(text)
    assert [item["name"] for item in habits] == ["exercise", "read", "meditate"]
    assert habits[0] == {"name": "exercise", "done": True, "streak": 12}
    assert habits[1]["done"] is False
    assert habits[2] == {"name": "meditate", "done": True, "streak": 3}


def test_parse_habit_list_empty_is_error() -> None:
    with pytest.raises(ADAPTER.HabitctlError) as info:
        ADAPTER.parse_habit_list("no habits here\n")
    assert info.value.code == "empty_habit_list"


def test_summarize_counts() -> None:
    summary = ADAPTER.summarize(
        [
            {"name": "a", "done": True, "streak": 4},
            {"name": "b", "done": False, "streak": 9},
        ]
    )
    assert summary == {"count": 2, "doneToday": 1, "bestStreak": 9, "totalStreak": 13}


def test_build_log_entry_rejects_bad_date() -> None:
    with pytest.raises(ADAPTER.HabitctlError) as info:
        ADAPTER.build_log_entry({"name": "walk", "date": "2026-13-40"})
    assert info.value.code == "invalid_input"


def test_handle_list_with_inline_text() -> None:
    result = MAIN.handle("habits.list", {"text": "[x] stretch streak=2\n"})
    assert result["habits"][0]["name"] == "stretch"
    assert result["habits"][0]["streakText"] == "连续 2 天"
    assert result["summary"]["bestStreak"] == 2


def test_handle_log_missing_name_is_rpc_error() -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("habits.log", {"date": "2026-10-31"})
    assert info.value.code == -32602
    assert info.value.data["code"] == "invalid_input"


def test_initialize_and_unknown_method() -> None:
    assert MAIN.handle("initialize", {"apiVersion": "1.0"})["moduleId"] == "io.github.blinry.habitctl"
    with pytest.raises(MAIN.RpcError):
        MAIN.handle("nope", {})

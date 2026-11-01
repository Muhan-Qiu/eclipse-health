"""io.github.jrnl-org.jrnl · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "jrnl"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
SAMPLE = json.dumps(
    [
        {"title": "Morning", "body": "slept well, mood ok", "date": "2026-10-30", "tags": ["mood"], "starred": False},
        {"title": "Run", "body": "5k easy", "date": "2026-10-31", "tags": ["mood", "sport"]},
    ]
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_jrnl_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.jrnl-org.jrnl"
    assert "llm" in manifest.permissions
    assert manifest.dependencies == ("jrnl>=4.0,<5",)


def test_parse_export_sorts_and_normalizes() -> None:
    entries = ADAPTER.parse_export(SAMPLE)
    assert [item["title"] for item in entries] == ["Run", "Morning"]
    assert entries[0]["tags"] == ["mood", "sport"]


def test_parse_export_rejects_invalid_json() -> None:
    with pytest.raises(ADAPTER.JournalError) as info:
        ADAPTER.parse_export("{not json")
    assert info.value.code == "invalid_json"


def test_search_by_text_and_tags() -> None:
    entries = ADAPTER.parse_export(SAMPLE)
    assert [item["title"] for item in ADAPTER.search(entries, "slept")] == ["Morning"]
    assert [item["title"] for item in ADAPTER.search(entries, "easy", tags=["sport"])] == ["Run"]
    assert ADAPTER.search(entries, "easy", tags=["mood", "missing"]) == []


def test_search_rejects_empty_query() -> None:
    with pytest.raises(ADAPTER.JournalError):
        ADAPTER.search([], "  ")


def test_handle_list_from_inline_text() -> None:
    result = MAIN.handle("journal.list", {"text": SAMPLE})
    assert result["summary"]["total"] == 2
    assert result["summary"]["tagCounts"]["mood"] == 2


def test_handle_get_not_found() -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("journal.get", {"text": SAMPLE, "title": "missing"})
    assert info.value.data["code"] == "not_found"

"""io.github.coddingtonbear.myfitnesspal 模块测试：manifest、纯函数 adapter、worker。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import load_manifest_file

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "python-myfitnesspal"


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_myfitnesspal", MODULE_DIR / "src" / "adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rpc(requests: list[dict]) -> list[dict]:
    text = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"
    completed = subprocess.run(
        [sys.executable, str(MODULE_DIR / "src" / "main.py")],
        check=False,
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


DIARY = {
    "date": "2026-10-30",
    "meals": {
        "breakfast": [
            {"name": "燕麦粥", "calories": 350, "proteinG": 12, "carbsG": 60, "fatG": 6},
            {"name": "牛奶", "calories": 120, "proteinG": 8},
        ],
        "lunch": [{"name": "米饭", "calories": 400}],
    },
}


def test_manifest_matches_schema_and_parses() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    parsed = load_manifest_file(MODULE_DIR / "module.json")
    assert parsed.id == "io.github.coddingtonbear.myfitnesspal"
    assert parsed.type.value == "data-source"
    assert any(dep.startswith("myfitnesspal") for dep in parsed.dependencies)


def test_normalize_diary(adapter) -> None:
    records = adapter.normalize_diary(DIARY)
    assert len(records) == 3
    assert {record["payload"]["meal"] for record in records} == {"breakfast", "lunch"}
    assert records[0]["payload"]["capturedAt"] == "2026-10-30T00:00:00Z"
    assert records[0]["recordType"] == "nutrition.entry"


def test_summarize_diary(adapter) -> None:
    summary = adapter.summarize_records(adapter.normalize_diary(DIARY))
    assert summary["latest"]["calories"] == 870.0
    assert summary["latest"]["at"] == "2026-10-30T00:00:00Z"


def test_invalid_diary_is_rejected(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_diary({"date": "2026-10-30", "meals": {"lunch": [{"name": ""}]}})
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_diary({"date": "2026-02-30", "meals": {}})


def test_worker_import_and_invalid_input() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "import", "params": {"payload": DIARY}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"payload": {"date": "oops"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.coddingtonbear.myfitnesspal"
    assert replies[1]["result"]["count"] == 3
    assert replies[2]["error"]["data"]["code"] == "INVALID_INPUT"


def test_upstream_library_importable() -> None:
    pytest.importorskip("myfitnesspal")

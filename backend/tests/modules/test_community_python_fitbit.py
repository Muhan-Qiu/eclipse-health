"""io.github.orcasgit.fitbit 模块测试：manifest、纯函数 adapter、stdio worker。"""

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
MODULE_DIR = ROOT / "modules" / "community" / "python-fitbit"


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_fitbit", MODULE_DIR / "src" / "adapter.py"
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


def test_manifest_matches_schema_and_parses() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    parsed = load_manifest_file(MODULE_DIR / "module.json")
    assert parsed.id == "io.github.orcasgit.fitbit"
    assert parsed.type.value == "data-source"
    assert parsed.entry_path == "src/main.py"
    assert any(dep.startswith("fitbit") for dep in parsed.dependencies)
    assert parsed.contributes["sources"][0]["id"] == "fitbit-web-api"


def test_parse_date_range(adapter) -> None:
    assert adapter.parse_date_range({"startDate": "2026-10-01", "endDate": "2026-10-02"}) == (
        "2026-10-01",
        "2026-10-02",
    )


def test_parse_date_range_rejects_bad_input(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.parse_date_range({"startDate": "2026-13-01", "endDate": "2026-10-02"})
    with pytest.raises(adapter.AdapterError):
        adapter.parse_date_range({"startDate": "2026-09-01", "endDate": "2026-10-10"})


def test_normalize_activity_and_summary(adapter) -> None:
    record = adapter.normalize_activity_day(
        {
            "date": "2026-10-31",
            "summary": {
                "steps": 4321,
                "caloriesOut": 2100.5,
                "lightlyActiveMinutes": 10,
                "fairlyActiveMinutes": 5,
                "veryActiveMinutes": 5,
            },
        }
    )
    payload = record["payload"]
    assert record["recordType"] == "activity.session"
    assert payload["steps"] == 4321
    assert payload["activeMinutes"] == 20
    summary = adapter.summarize_records([record])
    assert summary["latest"]["steps"] == 4321


def test_invalid_kind_is_rejected(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.records_from_export({"activities": []}, "unknown")
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_weight_log({"date": "2026-10-31", "weight": -3})


def test_worker_health_and_import() -> None:
    payload = {
        "activities": [
            {
                "date": "2026-10-30",
                "summary": {"steps": 1234, "caloriesOut": 900},
            }
        ]
    }
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "health", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"kind": "activity", "payload": payload}},
            {"jsonrpc": "2.0", "id": 4, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.orcasgit.fitbit"
    assert replies[1]["result"]["ok"] is True
    assert replies[2]["result"]["count"] == 1
    assert replies[2]["result"]["records"][0]["payload"]["steps"] == 1234


def test_worker_rejects_bad_import() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "import", "params": {"kind": "bogus"}},
            {"jsonrpc": "2.0", "id": 2, "method": "nope", "params": {}},
        ]
    )
    assert replies[0]["error"]["data"]["code"] == "INVALID_INPUT"
    assert replies[1]["error"]["data"]["code"] == "METHOD_NOT_FOUND"


def test_upstream_library_importable() -> None:
    pytest.importorskip("fitbit")

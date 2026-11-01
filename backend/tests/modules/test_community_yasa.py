"""官方模块 io.github.raphaelvallat.yasa 的 manifest、适配层与 worker 测试。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "yasa"
MAIN = MODULE_DIR / "src" / "main.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("yasa_adapter", MODULE_DIR / "src" / "adapter.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(lines: list[dict]) -> list[dict]:
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n"
    proc = subprocess.run(
        [sys.executable, str(MAIN)], input=payload.encode("utf-8"), capture_output=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]


def test_manifest_matches_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["id"] == "io.github.raphaelvallat.yasa"
    assert manifest["contributes"]["recordTypes"][0]["id"] == "sleep.session"


def test_sleep_efficiency_success() -> None:
    adapter = _load_adapter()
    result = adapter.sleep_efficiency(["W", "N1", "N2", "REM", "R", "W", "W", "N2"])
    assert result["epochs"] == 8
    assert result["totalMinutes"] == 4.0
    assert result["stageCounts"]["R"] == 2
    assert result["efficiency"] == 62.5
    assert adapter.stage_rows(result["stageCounts"], 30)[0]["stage"] == "N1"


@pytest.mark.parametrize(
    "bad",
    [[], ["ZZZ"], [1, 2], "W,N1"],
    ids=["empty", "unknown-stage", "non-string", "not-a-list"],
)
def test_invalid_stages_are_rejected(bad) -> None:
    adapter = _load_adapter()
    with pytest.raises(adapter.AdapterError):
        adapter.parse_stages(bad)


def test_worker_rpc_success_and_error() -> None:
    responses = _run(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"apiVersion": "1.0"}},
            {"jsonrpc": "2.0", "id": 2, "method": "analyze", "params": {"stages": ["W", "N2", "N3", "R"]}},
            {"jsonrpc": "2.0", "id": 3, "method": "analyze", "params": {"stages": ["BAD"]}},
            {"jsonrpc": "2.0", "id": 4, "method": "stats", "params": {}},
            {"jsonrpc": "2.0", "id": 5, "method": "sleep.efficiency", "params": {"stages": ["W", "N1"]}},
            {"jsonrpc": "2.0", "id": 6, "method": "deactivate", "params": {}},
        ]
    )
    by_id = {item["id"]: item for item in responses}
    assert by_id[1]["result"]["moduleId"] == "io.github.raphaelvallat.yasa"
    assert by_id[2]["result"]["efficiency"] == 75.0
    assert by_id[3]["error"]["data"]["code"] == "INVALID_INPUT"
    assert by_id[4]["result"]["latest"]["efficiency"] == 0.0
    assert by_id[5]["result"]["efficiency"] == 50.0
    assert by_id[6]["result"]["ok"] is True

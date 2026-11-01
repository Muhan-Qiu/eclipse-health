"""官方模块 io.github.pgomes92.pyhrv 的 manifest、适配层与 worker 测试。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "pyhrv"
MAIN = MODULE_DIR / "src" / "main.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("pyhrv_adapter", MODULE_DIR / "src" / "adapter.py")
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
    assert manifest["id"] == "io.github.pgomes92.pyhrv"
    assert any(item.startswith("pyhrv") for item in manifest["dependencies"])


def test_time_domain_and_mapping() -> None:
    adapter = _load_adapter()
    rr = adapter.parse_rr([800, 810, 790, 820, 805, 815])
    metrics = adapter.time_domain(rr)
    assert metrics["intervals"] == 6
    assert 73 <= metrics["meanHr"] <= 76
    mapped = adapter.map_pyhrv_time({"nni_mean": 805.0, "hr_mean": 74.5, "sdnn": 41.2, "rmssd": 33.1, "pnn50": 6.0})
    assert mapped["meanRr"] == 805.0
    assert mapped["rmssd"] == 33.1
    assert len(adapter.metric_rows(mapped)) == 5


@pytest.mark.parametrize(
    "bad",
    [[], [800], [1000, "x"], [1000, 100], [1000, 4000]],
    ids=["empty", "one", "non-numeric", "too-small", "too-large"],
)
def test_invalid_rr_is_rejected(bad) -> None:
    adapter = _load_adapter()
    with pytest.raises(adapter.AdapterError):
        adapter.parse_rr(bad)


def test_worker_rpc_success_and_error() -> None:
    responses = _run(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"apiVersion": "1.0"}},
            {"jsonrpc": "2.0", "id": 2, "method": "analyze", "params": {"rr": [800, 810, 790, 820]}},
            {"jsonrpc": "2.0", "id": 3, "method": "analyze", "params": {"rr": [900]}},
            {"jsonrpc": "2.0", "id": 4, "method": "stats", "params": {}},
            {"jsonrpc": "2.0", "id": 5, "method": "deactivate", "params": {}},
        ]
    )
    by_id = {item["id"]: item for item in responses}
    assert by_id[1]["result"]["moduleId"] == "io.github.pgomes92.pyhrv"
    assert by_id[2]["result"]["hrv"]["intervals"] == 4
    assert "upstreamTime" in by_id[2]["result"] or "upstreamError" in by_id[2]["result"]
    assert by_id[3]["error"]["data"]["code"] == "INVALID_INPUT"
    assert by_id[4]["result"]["latest"]["rmssd"] == 0.0
    assert by_id[5]["result"]["ok"] is True

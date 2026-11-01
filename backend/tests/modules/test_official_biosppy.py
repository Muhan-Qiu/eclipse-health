"""官方模块 io.github.scientisst.biosppy 的 manifest、适配层与 worker 测试。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "biosppy"
MAIN = MODULE_DIR / "src" / "main.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("biosppy_adapter", MODULE_DIR / "src" / "adapter.py")
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
    assert manifest["id"] == "io.github.scientisst.biosppy"
    assert any(item.startswith("biosppy") for item in manifest["dependencies"])


def test_rpeaks_to_rr_success() -> None:
    adapter = _load_adapter()
    rr = adapter.rpeaks_to_rr([0, 250, 500, 750, 1000], 250)
    assert rr == [1000.0, 1000.0, 1000.0, 1000.0]
    metrics = adapter.time_domain(rr)
    assert metrics["meanRr"] == 1000.0
    assert metrics["meanHr"] == 60.0
    assert metrics["rmssd"] == 0.0


@pytest.mark.parametrize(
    "peaks,fs",
    [([0, 1], 250), ([0, 250, 500], 0), ("x", 250), ([0, 250, 500], -1)],
    ids=["too-few-peaks", "zero-fs", "non-array", "negative-fs"],
)
def test_invalid_peaks_are_rejected(peaks, fs) -> None:
    adapter = _load_adapter()
    with pytest.raises(adapter.AdapterError):
        adapter.rpeaks_to_rr(peaks, fs)


def test_worker_rpc_success_and_error() -> None:
    responses = _run(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"apiVersion": "1.0"}},
            {"jsonrpc": "2.0", "id": 2, "method": "analyze", "params": {"rr": [800, 810, 790, 820]}},
            {"jsonrpc": "2.0", "id": 3, "method": "analyze", "params": {"rr": [900]}},
            {"jsonrpc": "2.0", "id": 4, "method": "ecg.quality", "params": {"rr": [800, 810]}},
            {"jsonrpc": "2.0", "id": 5, "method": "deactivate", "params": {}},
        ]
    )
    by_id = {item["id"]: item for item in responses}
    assert by_id[1]["result"]["moduleId"] == "io.github.scientisst.biosppy"
    assert by_id[2]["result"]["nPeaks"] == 5
    assert by_id[2]["result"]["hrv"]["intervals"] == 4
    assert by_id[3]["error"]["data"]["code"] == "INVALID_INPUT"
    assert by_id[4]["result"]["accepted"] is False
    assert by_id[5]["result"]["ok"] is True

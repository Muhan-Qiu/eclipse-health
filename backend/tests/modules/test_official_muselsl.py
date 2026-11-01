"""io.github.alexandrebarachant.muselsl 模块测试：manifest、CSV adapter、worker。"""

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
MODULE_DIR = ROOT / "modules" / "official" / "muselsl"

CSV_TEXT = (
    "timestamps,TP9,AF7,AF8,TP10\n"
    "0.000,1.0,-1.0,0.5,-0.5\n"
    "0.004,2.0,-2.0,1.0,-1.0\n"
    "0.008,3.0,-3.0,1.5,-1.5"
)


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_muselsl", MODULE_DIR / "src" / "adapter.py"
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
    assert parsed.id == "io.github.alexandrebarachant.muselsl"
    assert parsed.type.value == "device-adapter"
    assert parsed.contributes["importFormats"][0]["ext"] == ["csv"]


def test_parse_csv(adapter) -> None:
    parsed = adapter.parse_csv(CSV_TEXT)
    assert parsed["channelNames"] == ["TP9", "AF7", "AF8", "TP10"]
    assert parsed["sampleCount"] == 3
    assert parsed["sampleRate"] == 250.0
    assert parsed["durationSeconds"] == 0.008
    assert parsed["quality"]["overall"] == 100.0
    record = adapter.summarize_recording(parsed, "muse-2", "2026-10-31T00:00:00Z")
    assert record["payload"]["durationMinutes"] == 0.0
    assert record["payload"]["channelCount"] == 4


def test_parse_csv_rejects_bad_rows(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.parse_csv("timestamps,TP9\n0.000,abc\n")
    with pytest.raises(adapter.AdapterError):
        adapter.parse_csv("timestamps,TP9\n")
    with pytest.raises(adapter.AdapterError):
        adapter.build_stream_command("unknown-preset")


def test_stream_command(adapter) -> None:
    assert adapter.build_stream_command("muse-2") == ["muselsl", "stream", "--preset", "muse-2"]
    assert adapter.build_stream_command("muse-2", "AA:BB:CC:DD:EE:FF")[-2:] == [
        "--address",
        "AA:BB:CC:DD:EE:FF",
    ]
    with pytest.raises(adapter.AdapterError):
        adapter.build_stream_command("muse-2", "bad address!")


def test_worker_import_and_errors() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "import", "params": {"payload": CSV_TEXT}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"payload": 5}},
            {"jsonrpc": "2.0", "id": 4, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.alexandrebarachant.muselsl"
    assert replies[1]["result"]["count"] == 1
    assert replies[1]["result"]["records"][0]["payload"]["sampleRate"] == 250.0
    assert replies[2]["error"]["data"]["code"] == "INVALID_INPUT"


def test_upstream_library_importable() -> None:
    pytest.importorskip("muselsl")

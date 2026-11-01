"""io.github.openbci-archive.openbci 模块测试：manifest、文本 adapter、worker。"""

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
MODULE_DIR = ROOT / "modules" / "official" / "openbci-python"

# 8 通道 Cyton 文本：% 头注释 + 每行 样本序号 + 8 通道 + 额外列。
ROWS = ["%OpenBCI Raw EXG Data"]
for sample in range(3):
    channels = ",".join(str(value + sample) for value in (1, -1, 2, -2, 1, -1, 2, -2))
    ROWS.append(f"{sample},{channels},0,0,0,0,0")
TEXT = "\n".join(ROWS)


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_openbci", MODULE_DIR / "src" / "adapter.py"
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
    assert parsed.id == "io.github.openbci-archive.openbci"
    assert parsed.type.value == "device-adapter"
    assert parsed.contributes["importFormats"][0]["ext"] == ["txt"]


def test_parse_text(adapter) -> None:
    parsed = adapter.parse_openbci_text(TEXT, board="cyton", sample_rate=250)
    assert parsed["channelNames"] == [f"ch{index}" for index in range(1, 9)]
    assert parsed["sampleCount"] == 3
    assert parsed["durationSeconds"] == 0.012
    assert parsed["quality"]["overall"] == 100.0
    record = adapter.summarize_recording(parsed, "cyton", "2026-10-31T00:00:00Z")
    assert record["payload"]["channelCount"] == 8


def test_parse_text_rejects_bad_rows(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.parse_openbci_text("%header only")
    with pytest.raises(adapter.AdapterError):
        adapter.parse_openbci_text("0,1,2\n")
    with pytest.raises(adapter.AdapterError):
        adapter.parse_openbci_text("x,1,2,3,4,5,6,7,8")


def test_ports_and_boards(adapter) -> None:
    assert adapter.resolve_port("COM3") == "COM3"
    assert adapter.resolve_port("/dev/ttyUSB0") == "/dev/ttyUSB0"
    with pytest.raises(adapter.AdapterError):
        adapter.resolve_port("..\\evil")
    assert adapter.resolve_board("cyton-daisy") == ("cyton-daisy", 16)


def test_worker_import_and_errors() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "devices.list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"payload": TEXT}},
            {"jsonrpc": "2.0", "id": 4, "method": "import", "params": {"payload": TEXT, "board": "bad"}},
            {"jsonrpc": "2.0", "id": 5, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.openbci-archive.openbci"
    assert any(item["board"] == "cyton" for item in replies[1]["result"]["items"])
    assert replies[2]["result"]["count"] == 1
    assert replies[2]["result"]["records"][0]["payload"]["channelCount"] == 8
    assert replies[3]["error"]["data"]["code"] == "INVALID_INPUT"


def test_upstream_library_importable() -> None:
    pytest.importorskip("openbci")

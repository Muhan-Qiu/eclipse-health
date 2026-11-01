"""io.github.brainflow-dev.brainflow 模块测试：manifest、纯函数 adapter、worker。"""

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
MODULE_DIR = ROOT / "modules" / "community" / "brainflow"


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_brainflow", MODULE_DIR / "src" / "adapter.py"
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


JSONL = "\n".join(
    [
        json.dumps(
            {
                "board": "synthetic",
                "sampleRate": 250,
                "capturedAt": "2026-10-31T00:00:00Z",
                "channels": [
                    {"name": "ch1", "samples": [1.0, -1.0, 2.0, -2.0]},
                    {"name": "ch2", "samples": [0.5, -0.5, 0.5, -0.5]},
                ],
            }
        )
    ]
)


def test_manifest_matches_schema_and_parses() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    parsed = load_manifest_file(MODULE_DIR / "module.json")
    assert parsed.id == "io.github.brainflow-dev.brainflow"
    assert parsed.type.value == "device-adapter"
    assert parsed.contributes["importFormats"][0]["ext"] == ["jsonl", "json"]
    assert parsed.dependencies == ("brainflow>=5.13,<6",)


def test_resolve_board(adapter) -> None:
    assert adapter.resolve_board("cyton") == ("cyton", 0)
    assert adapter.resolve_board(-1) == ("synthetic", -1)
    with pytest.raises(adapter.AdapterError):
        adapter.resolve_board("not-a-board")


def test_signal_quality(adapter) -> None:
    good = adapter.compute_signal_quality([[1.0, -1.0, 2.0, -2.0]])
    assert good["overall"] == 100.0
    assert good["ok"] is True
    flat = adapter.compute_signal_quality([[5.0, 5.0, 5.0]])
    assert flat["overall"] == 0.0
    with pytest.raises(adapter.AdapterError):
        adapter.compute_signal_quality([])


def test_records_from_jsonl(adapter) -> None:
    records = adapter.records_from_jsonl(JSONL)
    assert len(records) == 1
    payload = records[0]["payload"]
    assert payload["board"] == "synthetic"
    assert payload["channelCount"] == 2
    assert payload["quality"] == 100.0
    with pytest.raises(adapter.AdapterError):
        adapter.parse_jsonl("{not json}")


def test_worker_boards_import_and_errors() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "boards.list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"payload": JSONL}},
            {"jsonrpc": "2.0", "id": 4, "method": "import", "params": {"payload": "{bad"}},
            {"jsonrpc": "2.0", "id": 5, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.brainflow-dev.brainflow"
    assert any(item["name"] == "cyton" for item in replies[1]["result"]["items"])
    assert replies[2]["result"]["count"] == 1
    assert replies[2]["result"]["records"][0]["payload"]["quality"] == 100.0
    assert replies[3]["error"]["data"]["code"] == "INVALID_INPUT"


def test_upstream_library_importable() -> None:
    pytest.importorskip("brainflow")

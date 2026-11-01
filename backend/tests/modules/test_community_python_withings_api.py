"""io.github.vangorra.withings 模块测试：manifest、纯函数 adapter、worker。"""

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
MODULE_DIR = ROOT / "modules" / "community" / "python-withings-api"


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location(
        "eh_adapter_withings", MODULE_DIR / "src" / "adapter.py"
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


MEAS_PAYLOAD = {
    "status": 0,
    "body": {
        "measuregrps": [
            {
                "grpid": 1,
                "date": 1793318400,
                "measures": [
                    {"type": 1, "value": 70500, "unit": -3},
                    {"type": 6, "value": 205, "unit": -1},
                    {"type": 10, "value": 118, "unit": 0},
                    {"type": 9, "value": 76, "unit": 0},
                ],
            }
        ]
    },
}


def test_manifest_matches_schema_and_parses() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    parsed = load_manifest_file(MODULE_DIR / "module.json")
    assert parsed.id == "io.github.vangorra.withings"
    assert parsed.type.value == "data-source"
    assert parsed.allowed_hosts == ["wbsapi.withings.net", "account.withings.com"]


def test_scale_measure(adapter) -> None:
    assert adapter.scale_measure(70500, -3) == 70.5
    with pytest.raises(adapter.AdapterError):
        adapter.scale_measure(1, 9)


def test_normalize_measure_group(adapter) -> None:
    record = adapter.normalize_measure_group(MEAS_PAYLOAD["body"]["measuregrps"][0])
    payload = record["payload"]
    assert payload["weightKg"] == 70.5
    assert payload["fatRatioPct"] == 20.5
    assert payload["systolicMmHg"] == 118
    assert payload["diastolicMmHg"] == 76
    assert payload["capturedAt"].endswith("Z")


def test_invalid_group_is_rejected(adapter) -> None:
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_measure_group({"date": 1793318400, "measures": []})
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_measure_group({"date": 1, "measures": [{"type": 999, "value": 1, "unit": 0}]})


def test_token_response(adapter) -> None:
    assert adapter.parse_token_response({"body": {"access_token": "abc", "expires_in": 3600}})[
        "accessToken"
    ] == "abc"
    with pytest.raises(adapter.AdapterError):
        adapter.parse_token_response({"status": 401})


def test_worker_import_and_invalid_input() -> None:
    replies = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "import", "params": {"payload": MEAS_PAYLOAD}},
            {"jsonrpc": "2.0", "id": 3, "method": "import", "params": {"payload": {"body": {}}}},
            {"jsonrpc": "2.0", "id": 4, "method": "deactivate", "params": {}},
        ]
    )
    assert replies[0]["result"]["moduleId"] == "io.github.vangorra.withings"
    assert replies[1]["result"]["records"][0]["payload"]["weightKg"] == 70.5
    assert replies[2]["error"]["data"]["code"] == "INVALID_INPUT"


def test_upstream_http_dependency_importable() -> None:
    pytest.importorskip("requests")

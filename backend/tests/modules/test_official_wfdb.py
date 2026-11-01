"""io.github.mit-lcp.wfdb · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "wfdb"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_wfdb_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter
PARAMS = {
    "recordName": "rec test",
    "fs": 250,
    "channels": [[0.1, -0.2, 0.3, 0.0]],
    "sigName": ["a b"],
    "units": ["mV"],
}


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.mit-lcp.wfdb"
    assert manifest.type.value == "exporter"
    assert manifest.contributes["exporters"][0]["format"] == "csv"


def test_sanitize_record_name() -> None:
    assert ADAPTER.sanitize_record_name("rec test/../x") == "rectestx"
    with pytest.raises(ADAPTER.WfdbAdapterError):
        ADAPTER.sanitize_record_name("///")


def test_build_plan_rejects_mismatched_channels() -> None:
    with pytest.raises(ADAPTER.WfdbAdapterError) as info:
        ADAPTER.build_export_plan({**PARAMS, "channels": [[1.0], [1.0, 2.0]]})
    assert info.value.code == "channel_length_mismatch"


def test_build_plan_sanitizes_labels() -> None:
    plan = ADAPTER.build_export_plan(PARAMS)
    assert plan["recordName"] == "rectest"
    assert plan["sigName"] == ["a_b"]
    assert plan["fs"] == 250


def test_export_csv_success(tmp_path: Path) -> None:
    result = MAIN.handle("export.csv", {**PARAMS, "outputDir": str(tmp_path)})
    target = Path(result["path"])
    assert target.is_file()
    assert result["rows"] == 4
    assert target.read_text(encoding="utf-8").startswith("time_s,a_b")


def test_export_rejects_empty_channels(tmp_path: Path) -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("export.wfdb", {**PARAMS, "channels": [], "outputDir": str(tmp_path)})
    assert info.value.code == -32602


def test_wfdb_roundtrip_when_installed(tmp_path: Path) -> None:
    pytest.importorskip("wfdb")
    exported = MAIN.handle("export.wfdb", {**PARAMS, "outputDir": str(tmp_path)})
    assert exported["nSamples"] == 4
    assert {Path(item).suffix for item in exported["files"]} == {".hea", ".dat"}
    imported = MAIN.handle("import.wfdb", {"path": str(tmp_path / "rectest")})
    assert imported["record"]["nSamples"] == 4
    assert imported["record"]["channels"] == 1

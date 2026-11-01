"""io.github.holgern.pyedflib · manifest + adapter + worker 测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.manifest import parse_manifest

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "pyedflib"
SCHEMA = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
PARAMS = {
    "recordName": "edf_test",
    "fs": 200,
    "channels": [[1.0, 2.0, 3.0]],
    "labels": ["ECG Lead II"],
    "units": ["uV"],
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIN = _load("eh_test_pyedflib_main", MODULE_DIR / "src" / "main.py")
ADAPTER = MAIN.adapter


def test_manifest_matches_schema() -> None:
    data = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMA).validate(data)
    manifest = parse_manifest(data)
    assert manifest.id == "io.github.holgern.pyedflib"
    assert manifest.dependencies == ("pyedflib>=0.1.38,<1",)


def test_sanitize_label_truncates_to_edf_limit() -> None:
    assert ADAPTER.sanitize_label("ECG Lead II extended", "ch1") == "ECG Lead II exte"
    assert ADAPTER.sanitize_label("!!!", "ch1") == "ch1"


def test_build_plan_rejects_bad_range() -> None:
    with pytest.raises(ADAPTER.EdfAdapterError) as info:
        ADAPTER.build_edf_plan({**PARAMS, "physicalMin": 5, "physicalMax": 5})
    assert info.value.code == "invalid_range"


def test_build_plan_labels_and_lengths() -> None:
    plan = ADAPTER.build_edf_plan(PARAMS)
    assert plan["labels"] == ["ECG Lead II"]
    assert plan["nSamples"] if "nSamples" in plan else len(plan["channels"][0]) == 3
    with pytest.raises(ADAPTER.EdfAdapterError):
        ADAPTER.build_edf_plan({**PARAMS, "labels": ["a", "b"]})


def test_export_csv_success(tmp_path: Path) -> None:
    result = MAIN.handle("export.csv", {**PARAMS, "outputDir": str(tmp_path)})
    assert Path(result["path"]).is_file()
    assert result["rows"] == 3


def test_export_edf_missing_upstream_or_roundtrip(tmp_path: Path) -> None:
    if importlib.util.find_spec("pyedflib") is None:
        with pytest.raises(MAIN.RpcError) as info:
            MAIN.handle("export.edf", {**PARAMS, "outputDir": str(tmp_path)})
        assert info.value.data["code"] == "upstream_unavailable"
        return
    result = MAIN.handle("export.edf", {**PARAMS, "outputDir": str(tmp_path)})
    assert Path(result["path"]).is_file()
    imported = MAIN.handle("import.edf", {"path": result["path"]})
    assert imported["record"]["nSamples"] == 3


def test_export_rejects_missing_output_dir() -> None:
    with pytest.raises(MAIN.RpcError) as info:
        MAIN.handle("export.edf", PARAMS)
    assert info.value.code == -32602

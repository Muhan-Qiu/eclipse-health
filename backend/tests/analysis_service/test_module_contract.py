"""Cardia 模块 manifest / 打包契约，以及崩溃重启预算（契约 §5）。"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import zipfile
from pathlib import Path
from types import ModuleType as PyModule

import pytest
from analysis_service_helpers import CARDIA_DIR

from eclipse_health_backend.modules import package
from eclipse_health_backend.modules.constants import MAX_AUTOMATIC_RESTARTS
from eclipse_health_backend.modules.manifest import (
    ModuleType,
    check_compatibility,
    load_manifest_file,
)


def _load_module_main() -> PyModule:
    spec = importlib.util.spec_from_file_location(
        "cardia_module_main", CARDIA_DIR / "src" / "main.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # 不在源码目录留下 __pycache__（会破坏 checksums 覆盖）
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_manifest_is_valid_analysis_model() -> None:
    manifest = load_manifest_file(CARDIA_DIR / "module.json")
    check_compatibility(manifest, core_version="1.0.0")

    assert manifest.id == "org.eclipsehealth.cardia"
    assert manifest.type is ModuleType.ANALYSIS_MODEL
    assert manifest.permissions == ["files:user-selected"]

    models = manifest.contributes["models"]
    assert len(models) == 1
    card = models[0]
    assert card["id"] == "cardia-2.0"
    assert card["format"] == "onnx"
    assert card["output"]["classes"] == ["N", "SVEB", "VEB", "F"]
    assert card["modelCard"]["nonDiagnostic"] is True
    assert card["modelCard"]["limitations"]


def test_manifest_declares_bundled_weights() -> None:
    manifest = load_manifest_file(CARDIA_DIR / "module.json")
    card = manifest.contributes["models"][0]
    files = card["files"]
    assert len(files) == 1
    weight = CARDIA_DIR / files[0]["path"]
    assert weight.is_file()
    assert weight.name == "cardia_k4_best_sim.onnx"
    assert package.sha256_file(weight) == files[0]["sha256"]
    assert card["runtime"]["format"] == "onnx"
    assert card["preprocess"]["version"] == "2.0"
    assert card["modelCard"]["parametersNote"]


def test_module_prefers_bundled_weights_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模块自带权重 → 设置 EH_CARDIA_MODEL_PATH；缺失 → 不设置（分析库回退）。"""
    module = _load_module_main()
    monkeypatch.setenv("ECLIPSE_MODULE_DIR", str(tmp_path))
    monkeypatch.delenv("EH_CARDIA_MODEL_PATH", raising=False)
    try:
        assert module.configure_model() is None
        assert "EH_CARDIA_MODEL_PATH" not in os.environ

        models = tmp_path / "models"
        models.mkdir()
        weight = models / "cardia_k4_best_sim.onnx"
        weight.write_bytes(b"weights")
        assert module.configure_model() == weight
        assert os.environ["EH_CARDIA_MODEL_PATH"] == str(weight)
    finally:
        os.environ.pop("EH_CARDIA_MODEL_PATH", None)


def test_committed_checksums_cover_packaged_module(cardia_package: Path) -> None:
    committed = CARDIA_DIR / "checksums.json"
    assert committed.is_file(), "运行 scripts/pack_cardia.py 生成 checksums.json"

    with zipfile.ZipFile(cardia_package) as archive:
        names = set(archive.namelist())
        weight = archive.read("models/cardia_k4_best_sim.onnx")
    assert "module.json" in names
    assert "src/main.py" in names
    assert "README.md" in names
    assert "models/cardia_k4_best_sim.onnx" in names
    manifest = load_manifest_file(CARDIA_DIR / "module.json")
    assert hashlib.sha256(weight).hexdigest() == manifest.contributes["models"][0]["files"][0]["sha256"]

    # 打包目录的校验和与提交的 checksums.json 一致（源码未漂移）。
    warnings = package.verify_checksums(CARDIA_DIR)
    assert warnings == []


def test_crash_restart_budget_follows_contract() -> None:
    from eclipse_health_backend.modules.manager import ModuleManager

    assert MAX_AUTOMATIC_RESTARTS == 3
    manager = ModuleManager()
    try:
        assert manager.max_restarts == 3
    finally:
        manager.shutdown()

"""Cardia 模块 manifest / 打包契约，以及崩溃重启预算（契约 §5）。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from analysis_service_helpers import CARDIA_DIR

from eclipse_health_backend.modules import package
from eclipse_health_backend.modules.constants import MAX_AUTOMATIC_RESTARTS
from eclipse_health_backend.modules.manifest import (
    ModuleType,
    check_compatibility,
    load_manifest_file,
)


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


def test_committed_checksums_cover_packaged_module(cardia_package: Path) -> None:
    committed = CARDIA_DIR / "checksums.json"
    assert committed.is_file(), "运行 scripts/pack_cardia.py 生成 checksums.json"

    with zipfile.ZipFile(cardia_package) as archive:
        names = set(archive.namelist())
    assert "module.json" in names
    assert "src/main.py" in names
    assert "README.md" in names

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

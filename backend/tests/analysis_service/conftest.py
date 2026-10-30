"""分析服务测试夹具：Cardia 模块包、独立模块管理器、假引擎与直调模式。"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from analysis_service_helpers import CARDIA_DIR, fake_result
from sqlalchemy import Engine, create_engine

from eclipse_health_backend.analysis_service import AnalysisService, set_analysis_service
from eclipse_health_backend.modules import package as module_package
from eclipse_health_backend.modules.manager import ModuleManager

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
ONNX_MODULE_SOURCE = FIXTURES_DIR / "modules" / "onnx"
ONNX_MODEL_FILE = FIXTURES_DIR / "onnx" / "mul_1.onnx"


@pytest.fixture()
def cardia_package(tmp_path: Path) -> Path:
    """把 modules/official/cardia 复制到临时目录、重写校验和后打包。"""
    source = tmp_path / "cardia-src"
    shutil.copytree(
        CARDIA_DIR, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    module_package.write_checksums(source)
    output = tmp_path / "cardia-1.0.0.ehmod"
    module_package.pack_directory(source, output)
    return output


@pytest.fixture()
def module_manager(tmp_path: Path) -> Iterator[ModuleManager]:
    data_dir = tmp_path / "module-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    engine: Engine = create_engine(
        f"sqlite:///{(data_dir / 'modules.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    manager = ModuleManager(data_dir=data_dir, engine=engine)
    try:
        yield manager
    finally:
        manager.shutdown()
        engine.dispose()


@pytest.fixture()
def cardia_manager(module_manager: ModuleManager, cardia_package: Path) -> ModuleManager:
    module_manager.install(cardia_package, enable=True)
    return module_manager


@pytest.fixture()
def onnx_package(tmp_path: Path) -> Path:
    """A3 测试用 analysis-model 模块包：manifest + onnxruntime 自带 mul_1.onnx。"""
    source = tmp_path / "onnx-module"
    shutil.copytree(ONNX_MODULE_SOURCE, source)
    models = source / "models"
    models.mkdir()
    shutil.copyfile(ONNX_MODEL_FILE, models / "mul_1.onnx")
    module_package.write_checksums(source)
    output = tmp_path / "onnx-lab-0.1.0.ehmod"
    module_package.pack_directory(source, output)
    return output


@pytest.fixture()
def onnx_manager(module_manager: ModuleManager, onnx_package: Path) -> ModuleManager:
    module_manager.install(onnx_package, enable=True)
    return module_manager


@pytest.fixture()
def onnx_engines(
    monkeypatch: pytest.MonkeyPatch, onnx_manager: ModuleManager
) -> ModuleManager:
    """让引擎目录读取测试模块内核（不触碰全局单例）。"""
    import eclipse_health_backend.analysis_service.engines as engines_module

    monkeypatch.setattr(engines_module, "_module_manager", lambda: onnx_manager)
    return onnx_manager


@pytest.fixture()
def fake_analyze(monkeypatch: pytest.MonkeyPatch):
    """把 analysis.engine.analyze 换成假实现（只影响直调路径）。"""

    def _fake(signal: Any, options: Any) -> dict[str, Any]:
        return fake_result(signal, options)

    import eclipse_health_backend.analysis.engine as engine_module

    monkeypatch.setattr(engine_module, "analyze", _fake)
    return _fake


@pytest.fixture()
def no_onnx_prewarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """直调模式的预热不加载真实 ONNX（本机初始化约 150 秒）。"""
    import eclipse_health_backend.analysis.model as model_module

    monkeypatch.setattr(
        model_module,
        "prewarm",
        lambda *args, **kwargs: {"sessionInitSeconds": 0.01, "cached": False},
    )


@pytest.fixture()
def direct_service(
    client: Any, monkeypatch: pytest.MonkeyPatch, no_onnx_prewarm: None
) -> Iterator[AnalysisService]:
    """直调模式的服务；依赖 ``client`` 以确保 app lifespan 先跑完再替换单例。"""
    assert client is not None
    monkeypatch.setenv("EH_ANALYSIS_DIRECT", "1")
    service = AnalysisService(direct=True, start_warmup=False)
    set_analysis_service(service)
    try:
        yield service
    finally:
        service.shutdown()
        set_analysis_service(None)

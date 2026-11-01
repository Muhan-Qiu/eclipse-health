"""模块内核测试夹具：独立 SQLite engine + 临时数据目录 + 可再打包的 demo 模块。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from module_test_helpers import build_demo_package
from sqlalchemy import Engine, create_engine

from eclipse_health_backend.modules import api as module_api
from eclipse_health_backend.modules.manager import ModuleManager


@pytest.fixture()
def module_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def engine(module_data_dir: Path) -> Iterator[Engine]:
    module_data_dir.mkdir(parents=True, exist_ok=True)
    created = create_engine(
        f"sqlite:///{(module_data_dir / 'module-tests.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    yield created
    created.dispose()


@pytest.fixture()
def manager(module_data_dir: Path, engine: Engine) -> Iterator[ModuleManager]:
    instance = ModuleManager(data_dir=module_data_dir, engine=engine, call_timeout_s=1.0)
    try:
        yield instance
    finally:
        instance.shutdown()


@pytest.fixture()
def demo_package(tmp_path: Path) -> Path:
    return build_demo_package(tmp_path)


@pytest.fixture()
def api_client(manager: ModuleManager) -> Iterator[TestClient]:
    # 用同一个 engine/data_dir 重新初始化全局 manager，路由与测试共享数据库。
    module_api.init_module_system(engine=manager.engine, data_dir=manager.data_dir)
    manager.shutdown()
    app = FastAPI()
    app.include_router(module_api.router, prefix="/api/v1/modules")
    with TestClient(app) as client:
        yield client
    module_api.shutdown_module_system()

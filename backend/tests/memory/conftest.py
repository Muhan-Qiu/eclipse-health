"""记忆路由在指挥官统一挂载前先挂到测试 app 上；每个用例重置 memory.json。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from eclipse_health_backend.app import app
from eclipse_health_backend.memory.api import router as memory_router


def _mount() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    if "/api/v1/memory" not in paths:
        app.include_router(memory_router, prefix="/api/v1")


_mount()


@pytest.fixture(autouse=True)
def clean_memory_file(data_dir: Path) -> Iterator[None]:
    path = data_dir / "memory.json"
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)

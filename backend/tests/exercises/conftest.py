"""运动路由在指挥官统一挂载前先挂到测试 app 上。"""

from __future__ import annotations

from eclipse_health_backend.app import app
from eclipse_health_backend.exercises.api import router as exercises_router


def _mount() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    if "/api/v1/exercises" not in paths:
        app.include_router(exercises_router, prefix="/api/v1")


_mount()

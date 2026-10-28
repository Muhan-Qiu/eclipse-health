"""FastAPI 应用装配。

- 生命周期内完成建表与默认成员；
- ``/api/v1`` 为核心路由；
- B1-02 的模块路由用 try/except 挂载：``eclipse_health_backend.modules.api.router``
  不存在或导入失败时，核心服务照常启动。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import api_router
from .api.errors import install_error_handlers
from .db.base import init_db, session_scope
from .db.repositories import ensure_default_member
from .domain.common import utc_now
from .settings import get_settings

logger = logging.getLogger(__name__)

EXPOSED_HEADERS = [
    "ETag",
    "Content-Disposition",
    "X-Signal-Id",
    "X-Signal-Lead",
    "X-Signal-Fs",
    "X-Signal-Unit",
    "X-Signal-Samples",
    "X-Signal-Sha256",
]

API_DESCRIPTION = """
本地优先的健康数据服务：成员、健康记录、波形文件、分析结果。

- 分页：`limit` + `offset`，按 `capturedAt` 倒序。
- 软删除：`DELETE /records/{id}` 只标记 `deletedAt`，默认查询不再返回。
- 波形：`POST /records` 可内联 float32 数组或引用 `imports/` 下的文件；
  `GET /records/{id}/signal` 返回 `application/octet-stream` 小端 float32。
- 分析：`POST /records/{id}/analyses` 返回 202，轮询 `GET /analyses/{id}`；
  引擎就绪状态见 `GET /engine`（`warming|ready|error`）。
- 错误：所有业务错误返回 `{code, message, details}`。
"""


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    with session_scope() as session:
        ensure_default_member(session)
    app.state.started_at = utc_now()
    logger.info("backend ready db=%s data=%s", settings.db_path, settings.data_dir)
    _start_module_system()
    _start_analysis_service()
    try:
        yield
    finally:
        _stop_analysis_service()
        _stop_module_system()


def _start_module_system() -> None:
    try:
        from .modules.api import init_module_system
    except Exception:  # noqa: BLE001
        logger.info("module system not available; module APIs disabled")
        return
    try:
        init_module_system()
    except Exception:
        logger.exception("module system initialization failed")


def _stop_module_system() -> None:
    try:
        from .modules.api import shutdown_module_system
    except Exception:  # noqa: BLE001
        return
    try:
        shutdown_module_system()
    except Exception:
        logger.exception("module system shutdown failed")


def _start_analysis_service() -> None:
    """只装配服务；Cardia 预热在后台线程里进行，不阻塞 HTTP 就绪。"""
    try:
        from .analysis_service import init_analysis_service
    except Exception:  # noqa: BLE001
        logger.info("analysis service not available; analysis APIs disabled")
        return
    try:
        init_analysis_service()
    except Exception:
        logger.exception("analysis service initialization failed")


def _stop_analysis_service() -> None:
    try:
        from .analysis_service import shutdown_analysis_service
    except Exception:  # noqa: BLE001
        return
    try:
        shutdown_analysis_service()
    except Exception:
        logger.exception("analysis service shutdown failed")


def _mount_modules_router(app: FastAPI) -> None:
    """B1-02 契约：router 无前缀，核心挂到 ``/api/v1/modules``。"""
    try:
        from .modules.api import router as modules_router
    except Exception:  # noqa: BLE001 - 模块系统缺失/未完成时不能拖垮核心
        logger.info("modules router not available; skipping /api/v1/modules")
        return
    app.include_router(modules_router, prefix="/api/v1/modules")
    logger.info("modules router mounted at /api/v1/modules")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="eclipse health backend",
        description=API_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=EXPOSED_HEADERS,
    )
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    _mount_modules_router(app)
    return app


app = create_app()

"""``/api/v1`` 路由汇总。

B2-02 的导入路由在运行时挂载：``importers.api.router`` 不存在时服务照常启动。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import analyses, health, members, records

logger = logging.getLogger(__name__)

api_router = APIRouter()
api_router.include_router(analyses.router)
api_router.include_router(health.router)
api_router.include_router(members.router, prefix="/members")
api_router.include_router(records.router, prefix="/records")


def _mount_imports_router(router: APIRouter) -> None:
    """B2-02 契约：导入路由的路径自带 ``/imports``，直接挂到 ``/api/v1`` 下。"""
    try:
        from ..importers.api import router as imports_router
    except Exception:  # noqa: BLE001 - 导入模块缺失/未完成时不能拖垮核心
        logger.info("imports router not available; skipping /api/v1/imports")
        return
    router.include_router(imports_router)
    logger.info("imports router mounted at /api/v1/imports")


_mount_imports_router(api_router)

__all__ = ["api_router"]

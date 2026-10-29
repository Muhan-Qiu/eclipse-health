"""``/api/v1`` 路由汇总。

B2-02 的导入路由在运行时挂载：``importers.api.router`` 不存在时服务照常启动。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import analyses, health, members, records, trends

logger = logging.getLogger(__name__)

api_router = APIRouter()
api_router.include_router(analyses.router)
api_router.include_router(health.router)
api_router.include_router(members.router, prefix="/members")
api_router.include_router(records.router, prefix="/records")
# B3-02：趋势路由路径自带 /trends，不加前缀。
api_router.include_router(trends.router)


def _mount_imports_router(router: APIRouter) -> None:
    """B2-02 契约：导入路由的路径自带 ``/imports``，直接挂到 ``/api/v1`` 下。"""
    try:
        from ..importers.api import router as imports_router
    except Exception:  # noqa: BLE001 - 导入模块缺失/未完成时不能拖垮核心
        logger.info("imports router not available; skipping /api/v1/imports")
        return
    router.include_router(imports_router)
    logger.info("imports router mounted at /api/v1/imports")


def _mount_reports_router(router: APIRouter) -> None:
    """B3-03 契约：报告路由自带 ``/records/{id}/reports`` 与 ``/reports/{id}``。"""
    try:
        from .reports import router as reports_router
    except Exception:  # noqa: BLE001 - 报告模块缺失/未完成时不能拖垮核心
        logger.info("reports router not available; skipping /api/v1/reports")
        return
    router.include_router(reports_router)
    logger.info("reports router mounted at /api/v1/reports")


def _mount_assistant_router(router: APIRouter) -> None:
    """B3-04 契约：助手路由自带 ``/assistant`` 前缀。"""
    try:
        from .assistant import router as assistant_router
    except Exception:  # noqa: BLE001 - 助手模块缺失/未完成时不能拖垮核心
        logger.info("assistant router not available; skipping /api/v1/assistant")
        return
    router.include_router(assistant_router)
    logger.info("assistant router mounted at /api/v1/assistant")


_mount_imports_router(api_router)
_mount_reports_router(api_router)
_mount_assistant_router(api_router)

__all__ = ["api_router"]

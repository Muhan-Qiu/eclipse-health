"""``/api/v1`` 路由汇总。

B2-02 的导入路由、B4-07 的 metrics 路由在运行时挂载：
模块不存在或导入失败时服务照常启动。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import (
    analyses,
    diagnostics,
    export,
    external,
    health,
    members,
    privacy,
    records,
    settings,
    trends,
)

logger = logging.getLogger(__name__)

api_router = APIRouter()
api_router.include_router(analyses.router)
api_router.include_router(health.router)
api_router.include_router(members.router, prefix="/members")
api_router.include_router(records.router, prefix="/records")
# B3-02：趋势路由路径自带 /trends，不加前缀。
api_router.include_router(trends.router)
# B4-04：导出、隐私、诊断、桌面设置；路径均已自带前缀。
api_router.include_router(export.router)
api_router.include_router(privacy.router)
api_router.include_router(diagnostics.router)
api_router.include_router(settings.router)
# F3：对外 API（key 管理 + 只读 REST + OpenAI 兼容），路径自带 /external。
api_router.include_router(external.router)


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


def _mount_metrics_router(router: APIRouter) -> None:
    """B4-07 契约：``metrics.api.router`` 提供 ``/metrics/...``。

    若 router 内的路径已经以 ``/metrics`` 开头（与 trends 同样的约定），
    直接挂载；否则补上 ``/metrics`` 前缀。
    """
    try:
        from ..metrics.api import router as metrics_router
    except Exception:  # noqa: BLE001 - 指标模块未完成时不能拖垮核心
        logger.info("metrics router not available; skipping /api/v1/metrics")
        return
    try:
        paths = [str(getattr(route, "path", "")) for route in metrics_router.routes]
    except Exception:  # noqa: BLE001
        paths = []
    prefixed = any(path == "/metrics" or path.startswith("/metrics/") for path in paths)
    if prefixed:
        router.include_router(metrics_router)
    else:
        router.include_router(metrics_router, prefix="/metrics")
    logger.info("metrics router mounted at /api/v1/metrics")


_mount_imports_router(api_router)
_mount_reports_router(api_router)
_mount_assistant_router(api_router)
_mount_metrics_router(api_router)


def _mount_optional_router(module_name: str, prefix: str = "") -> None:
    """Stage F 路由：模块缺失/未完成时不拖垮核心。"""
    try:
        import importlib

        module = importlib.import_module(
            f"{__package__.rpartition('.')[0]}.{module_name}.api"
        )
        router = module.router
    except Exception:  # noqa: BLE001
        logger.info("%s router not available; skipping", module_name)
        return
    api_router.include_router(router, prefix=prefix)
    logger.info("%s router mounted", module_name)


_mount_optional_router("scoring")
_mount_optional_router("exercises")
_mount_optional_router("memory")
_mount_optional_router("coach")
_mount_optional_router("ohs")

__all__ = ["api_router"]

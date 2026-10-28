"""``/api/v1`` 路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from . import health, members, records

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(members.router, prefix="/members")
api_router.include_router(records.router, prefix="/records")

__all__ = ["api_router"]

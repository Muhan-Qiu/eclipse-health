"""``/api/v1/marketplace`` 路由；挂载前缀由 ``api/__init__.py`` 负责。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..modules.errors import ModuleError
from .config import MarketplaceConfig
from .errors import MarketplaceError, validate_source
from .index import load_public_keys
from .service import MarketplaceService

router = APIRouter(tags=["marketplace"])


def get_service() -> MarketplaceService:
    # 延迟导入：模块内核的初始化只在真正访问市场时才需要。
    from ..modules.api import get_manager

    return MarketplaceService(get_manager())


def _error(exc: MarketplaceError | ModuleError) -> JSONResponse:
    if isinstance(exc, MarketplaceError):
        return JSONResponse(status_code=exc.http_status, content=exc.to_http_detail())
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "details": exc.detail or None},
    )


class InstallRequest(BaseModel):
    source: str = Field(default="official", max_length=32)
    moduleId: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)


@router.get("/sources")
def list_sources() -> JSONResponse:
    config = MarketplaceConfig.from_env()
    try:
        key_ids = sorted(load_public_keys(config.public_key_path))
    except MarketplaceError:
        key_ids = []
    return JSONResponse(
        content={
            "official": {
                "url": config.official_url,
                "configured": bool(config.official_url),
            },
            "community": {
                "url": config.community_url,
                "configured": bool(config.community_url),
            },
            "keyIds": key_ids,
        }
    )


@router.get("/index")
def list_index(
    source: str = Query(default="official"),
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=64),
) -> JSONResponse:
    try:
        validate_source(source)
        payload = get_service().list_entries(source, query=q, category=category)
        return JSONResponse(content=jsonable_encoder(payload))
    except (MarketplaceError, ModuleError) as exc:
        return _error(exc)


@router.get("/updates")
def list_updates() -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(get_service().updates()))
    except (MarketplaceError, ModuleError) as exc:
        return _error(exc)


@router.post("/install")
def install_module(request: InstallRequest) -> JSONResponse:
    try:
        payload: dict[str, Any] = get_service().install(
            request.source, request.moduleId, request.version
        )
        return JSONResponse(content=jsonable_encoder(payload))
    except (MarketplaceError, ModuleError) as exc:
        return _error(exc)


__all__ = ["get_service", "router"]

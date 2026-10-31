"""``/api/v1/ohs`` 路由：设置、连接测试、日汇总同步。

路由前缀自带 ``/ohs``，由指挥官在 ``api/__init__.py`` 中挂到 ``/api/v1``；
本文件不修改挂载表。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import SessionDep
from ..db.repositories import ensure_default_member
from ..domain.errors import InvalidInputError
from . import store
from .client import OhsClient
from .sync import DEFAULT_DAYS, MAX_DAYS, sync_recent

router = APIRouter(prefix="/ohs", tags=["ohs"])


class OhsSettingsResponse(BaseModel):
    configured: bool
    baseUrl: str
    hasToken: bool
    userId: str | None = None
    lastSync: dict[str, Any] | None = None


class OhsSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseUrl: str = Field(min_length=1, max_length=500)
    token: str | None = Field(default=None, max_length=4096)
    userId: str | None = Field(default=None, max_length=128)


class OhsTestResponse(BaseModel):
    ok: bool
    baseUrl: str
    authType: str
    userCount: int
    users: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class OhsSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS)


class OhsSyncResponse(BaseModel):
    created: int
    skipped: int
    failed: int
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    userId: str | None = None
    days: int = DEFAULT_DAYS


def build_client(base_url: str, token: str) -> OhsClient:
    """测试可通过替换此工厂注入 mock transport。"""
    return OhsClient(base_url, token)


def _configured_client() -> OhsClient:
    config = store.load_config()
    if not config.token:
        raise InvalidInputError(
            "尚未配置 OHS token",
            code="ohs_not_configured",
        )
    return build_client(config.base_url, config.token)


@router.get("/settings", response_model=OhsSettingsResponse, summary="读取 OHS 设置")
def read_ohs_settings() -> OhsSettingsResponse:
    return OhsSettingsResponse(**store.public_settings())


@router.put("/settings", response_model=OhsSettingsResponse, summary="保存 OHS 设置")
def write_ohs_settings(payload: OhsSettingsUpdate) -> OhsSettingsResponse:
    saved = store.save_settings(payload.baseUrl, payload.token, payload.userId)
    return OhsSettingsResponse(**saved)


@router.post(
    "/test",
    response_model=OhsTestResponse,
    summary="测试 OHS 连接（只读）",
)
def test_ohs_connection() -> OhsTestResponse:
    client = _configured_client()
    try:
        info = client.test_connection()
    finally:
        client.close()
    return OhsTestResponse(**info)


@router.post("/sync", response_model=OhsSyncResponse, summary="同步 OHS 最近日汇总")
def sync_ohs(
    session: SessionDep,
    payload: OhsSyncRequest | None = None,
) -> OhsSyncResponse:
    member = ensure_default_member(session)
    result = sync_recent(
        session,
        member.id,
        days=payload.days if payload else DEFAULT_DAYS,
    )
    return OhsSyncResponse(**result.to_dict())


__all__ = ["router"]

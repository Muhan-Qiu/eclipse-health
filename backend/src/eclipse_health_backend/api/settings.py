"""桌面设置 API（H1/H2）。

设置存于 ``data/settings.json``；`telemetryEnabled` 永远为 false，开启会返回 422。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ..domain.errors import InvalidInputError
from ..privacy.settings_store import load_settings, save_settings

router = APIRouter(tags=["settings"])

AppLocale = Literal["zh-CN", "en-US"]


class SettingsResponse(BaseModel):
    closeToTray: bool
    splashEnabled: bool
    telemetryEnabled: bool
    locale: AppLocale | None = None


class SettingsUpdate(BaseModel):
    closeToTray: bool | None = None
    splashEnabled: bool | None = None
    telemetryEnabled: bool | None = None
    locale: AppLocale | None = None


@router.get("/settings", response_model=SettingsResponse, summary="读取桌面设置")
def read_settings() -> Any:
    return SettingsResponse(**load_settings())


@router.put(
    "/settings",
    response_model=SettingsResponse,
    summary="保存桌面设置",
    responses={422: {"description": "遥测不支持开启"}},
)
def write_settings(payload: SettingsUpdate) -> Any:
    if payload.telemetryEnabled is True:
        raise InvalidInputError(
            "telemetry is not implemented",
            code="telemetry_not_supported",
        )
    patch = payload.model_dump(exclude_unset=True)
    patch.pop("telemetryEnabled", None)
    return SettingsResponse(**save_settings(patch))


__all__ = ["router"]

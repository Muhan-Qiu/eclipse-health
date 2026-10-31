"""教练只读 API：``/api/v1/coach/context`` 与 ``/api/v1/coach/weather``。

路由自带 ``/coach`` 前缀；指挥官统一挂到 ``/api/v1``。天气失败只返回
``weather: null``，不影响上下文其余部分。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..api.deps import SessionDep
from .context import build_coach_context
from .weather import get_weather, normalize_city

router = APIRouter(prefix="/coach", tags=["coach"])

CityQuery = Annotated[str | None, Query(max_length=80)]


@router.get("/context", summary="教练上下文（评分/健康数据/运动/记忆/天气，只读）")
async def coach_context(session: SessionDep, city: CityQuery = None) -> dict[str, Any]:
    payload = build_coach_context(session)
    payload["weather"] = await get_weather(city)
    return payload


@router.get("/weather", summary="城市天气（Open-Meteo，失败返回 null）")
async def coach_weather(city: CityQuery = None) -> dict[str, Any]:
    weather = await get_weather(city)
    return {
        "city": normalize_city(city),
        "available": weather is not None,
        "weather": weather,
    }


__all__ = ["router"]

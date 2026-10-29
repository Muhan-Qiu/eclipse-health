"""趋势 API：``GET /trends``。

口径（与 Data Schema §7 一致）：

- 只有 ``completed`` 分析、未删除记录参与；
- 每条记录取最新一次完成分析，避免重复分析把同一天放大；
- 时间轴用记录的 ``capturedAt``（而不是分析时间），缺值的记录跳过，不用 0 填充；
- 默认最近 30 天；``from``/``to`` 为 RFC 3339。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import InvalidInputError
from ..trends import build_trends, parse_metrics
from .deps import SessionDep

router = APIRouter(tags=["trends"])

DEFAULT_WINDOW = timedelta(days=30)


class TrendPointModel(BaseModel):
    t: str
    value: float
    recordId: str
    analysisId: str


class TrendSummaryModel(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    count: int = 0


class TrendSeriesModel(BaseModel):
    metric: str
    label: str
    unit: str
    ucum: str
    points: list[TrendPointModel] = Field(default_factory=list)
    summary: TrendSummaryModel


class TrendsModel(BaseModel):
    series: list[TrendSeriesModel]


def _as_storage_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return to_storage_dt(value)


@router.get("/trends", response_model=TrendsModel, summary="按测量码查询历史趋势")
def get_trends(
    session: SessionDep,
    metrics: Annotated[
        str | None,
        Query(description="逗号分隔的测量码；默认 heart_rate_mean,rmssd"),
    ] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    member_id: Annotated[str | None, Query(alias="memberId")] = None,
) -> TrendsModel:
    codes = parse_metrics(metrics)
    since = _as_storage_datetime(from_)
    until = _as_storage_datetime(to)
    if since is None and until is None:
        since = to_storage_dt(utc_now() - DEFAULT_WINDOW)
    if since is not None and until is not None and since > until:
        raise InvalidInputError(
            "from must be earlier than or equal to to",
            code="invalid_range",
            details={"from": from_.isoformat(), "to": to.isoformat()},
        )

    series: list[dict[str, Any]] = build_trends(
        session,
        metrics=codes,
        since=since,
        until=until,
        member_id=member_id,
    )
    return TrendsModel(series=series)


__all__ = ["router"]

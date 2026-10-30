"""手动指标 API：``/api/v1/metrics``。

路径自带 ``/metrics`` 前缀；``api/__init__.py`` 会按前缀检测直接挂载。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from ..api.deps import SessionDep
from ..db.models import RecordTable
from ..db.repositories import (
    add_record,
    ensure_default_member,
    get_member_row,
    get_record_row,
    record_from_row,
    update_record_row,
)
from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import InvalidInputError, not_found
from ..domain.ids import new_id
from ..domain.models import HealthRecord
from .models import (
    METRIC_RECORD_TYPE,
    Metric,
    MetricCreate,
    MetricKind,
    MetricPage,
    MetricUpdate,
    normalize_values,
)
from .service import build_metric_record, metric_from_row, metric_payload

router = APIRouter(tags=["metrics"])


def _as_storage_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return to_storage_dt(value)


def _require_metric(session: Session, metric_id: str) -> RecordTable:
    row = get_record_row(session, metric_id)
    if row is None or row.deleted_at is not None or row.record_type != METRIC_RECORD_TYPE:
        raise not_found("metric", metric_id)
    return row


def _parse_values(kind: MetricKind, raw: dict[str, float]) -> dict[str, float]:
    try:
        return normalize_values(kind, raw)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "invalid metric values",
            code="invalid_metric_values",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def _to_metric(row: RecordTable) -> Metric:
    metric = metric_from_row(row)
    if metric is None:
        raise InvalidInputError(
            "metric payload is invalid",
            code="invalid_metric_payload",
            details={"id": row.id},
        )
    return metric


@router.post("", response_model=Metric, status_code=status.HTTP_201_CREATED, summary="录入手动指标")
def create_metric(payload: MetricCreate, session: SessionDep) -> Metric:
    values = _parse_values(payload.kind, payload.values)

    if payload.memberId is None:
        member_id = ensure_default_member(session).id
    else:
        if get_member_row(session, payload.memberId) is None:
            raise not_found("member", payload.memberId)
        member_id = payload.memberId

    now = utc_now()
    record = build_metric_record(
        record_id=new_id("record"),
        member_id=member_id,
        kind=payload.kind,
        measured_at=payload.measuredAt,
        timezone=payload.timezone,
        values=values,
        notes=payload.notes,
        tags=payload.tags,
        created_at=now,
        updated_at=now,
    )
    add_record(session, record, commit=False)
    session.commit()
    row = get_record_row(session, record.id)
    assert row is not None  # 刚刚写入
    return _to_metric(row)


@router.get("", response_model=MetricPage, summary="分页列出手动指标")
def list_metrics(
    session: SessionDep,
    kind: Annotated[MetricKind | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MetricPage:
    conditions = [
        RecordTable.record_type == METRIC_RECORD_TYPE,
        RecordTable.deleted_at.is_(None),
    ]
    if kind is not None:
        conditions.append(RecordTable.payload["kind"].as_string() == kind.value)
    since = _as_storage_datetime(from_)
    until = _as_storage_datetime(to)
    if since is not None:
        conditions.append(RecordTable.captured_at >= since)
    if until is not None:
        conditions.append(RecordTable.captured_at <= until)

    total = session.exec(
        select(func.count()).select_from(RecordTable).where(*conditions)
    ).one()
    statement = (
        select(RecordTable)
        .where(*conditions)
        .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items: list[Metric] = []
    for row in session.exec(statement):
        metric = metric_from_row(row)
        if metric is not None:
            items.append(metric)
    return MetricPage(items=items, total=int(total), limit=limit, offset=offset)


@router.patch("/{metric_id}", response_model=Metric, summary="更新手动指标")
def patch_metric(metric_id: str, payload: MetricUpdate, session: SessionDep) -> Metric:
    row = _require_metric(session, metric_id)
    current = record_from_row(row)
    current_metric = _to_metric(row)

    merged = current.model_dump(by_alias=True, mode="json")
    updates = payload.model_dump(exclude_unset=True, by_alias=True, mode="json")
    if "values" in updates and updates["values"] is not None:
        values = _parse_values(current_metric.kind, updates.pop("values"))
        merged["payload"] = metric_payload(current_metric.kind, values)
    if "measuredAt" in updates and updates["measuredAt"] is not None:
        merged["capturedAt"] = updates.pop("measuredAt")
    merged.update(updates)
    merged["updatedAt"] = utc_now()

    try:
        updated = HealthRecord.model_validate(merged)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "metric validation failed",
            code="metric_invalid",
            details={"errors": exc.errors(include_url=False)},
        ) from exc
    update_record_row(session, row, updated)
    return _to_metric(row)


@router.delete("/{metric_id}", status_code=status.HTTP_204_NO_CONTENT, summary="软删除手动指标")
def delete_metric(metric_id: str, session: SessionDep) -> Response:
    row = _require_metric(session, metric_id)
    current = record_from_row(row)
    now = utc_now()
    merged = current.model_dump(by_alias=True, mode="json")
    merged["deletedAt"] = now
    merged["updatedAt"] = now
    update_record_row(session, row, HealthRecord.model_validate(merged))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

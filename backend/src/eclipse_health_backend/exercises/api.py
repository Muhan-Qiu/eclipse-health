"""运动记录 API：``/api/v1/exercises``。

路由自带 ``/exercises`` 前缀；由 ``api/__init__.py`` 统一挂载到 ``/api/v1``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from fastapi.encoders import jsonable_encoder
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
from .models import EXERCISE_RECORD_TYPE, Exercise, ExerciseCreate, ExercisePage, ExerciseUpdate
from .service import build_exercise_record, exercise_from_row

router = APIRouter(prefix="/exercises", tags=["exercises"])


def _as_storage_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return to_storage_dt(value)


def _require_exercise(session: Session, exercise_id: str) -> RecordTable:
    row = get_record_row(session, exercise_id)
    if row is None or row.deleted_at is not None or row.record_type != EXERCISE_RECORD_TYPE:
        raise not_found("exercise", exercise_id)
    return row


def _to_exercise(row: RecordTable) -> Exercise:
    exercise = exercise_from_row(row)
    if exercise is None:
        raise InvalidInputError(
            "exercise payload is invalid",
            code="invalid_exercise_payload",
            details={"id": row.id},
        )
    return exercise


def _build(**kwargs: Any) -> HealthRecord:
    try:
        return build_exercise_record(**kwargs)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "exercise validation failed",
            code="exercise_invalid",
            details={
                "errors": jsonable_encoder(
                    exc.errors(include_url=False), custom_encoder={Exception: str}
                )
            },
        ) from exc


@router.post("", response_model=Exercise, status_code=status.HTTP_201_CREATED, summary="新增运动记录")
def create_exercise(payload: ExerciseCreate, session: SessionDep) -> Exercise:
    if payload.memberId is None:
        member_id = ensure_default_member(session).id
    else:
        if get_member_row(session, payload.memberId) is None:
            raise not_found("member", payload.memberId)
        member_id = payload.memberId

    now = utc_now()
    record = _build(
        record_id=new_id("record"),
        member_id=member_id,
        activity=payload.activity,
        duration_sec=payload.durationSec,
        distance_km=payload.distanceKm,
        intensity=payload.intensity,
        subjective=payload.subjective,
        notes=payload.notes,
        start_at=payload.startAt,
        source=payload.source,
        timezone=payload.timezone,
        created_at=now,
        updated_at=now,
    )
    add_record(session, record, commit=False)
    session.commit()
    row = get_record_row(session, record.id)
    assert row is not None  # 刚刚写入
    return _to_exercise(row)


@router.get("", response_model=ExercisePage, summary="按时间倒序列出运动记录")
def list_exercises(
    session: SessionDep,
    activity: Annotated[str | None, Query(max_length=16)] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExercisePage:
    conditions = [
        RecordTable.record_type == EXERCISE_RECORD_TYPE,
        RecordTable.deleted_at.is_(None),
    ]
    if activity is not None:
        conditions.append(RecordTable.payload["activity"].as_string() == activity)
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
    items: list[Exercise] = []
    for row in session.exec(statement):
        exercise = exercise_from_row(row)
        if exercise is not None:
            items.append(exercise)
    return ExercisePage(items=items, total=int(total), limit=limit, offset=offset)


@router.patch("/{exercise_id}", response_model=Exercise, summary="更新运动记录")
def patch_exercise(exercise_id: str, payload: ExerciseUpdate, session: SessionDep) -> Exercise:
    row = _require_exercise(session, exercise_id)
    current = _to_exercise(row)
    updates = payload.model_dump(exclude_unset=True)
    timezone = updates.pop("timezone", None) or record_from_row(row).timezone
    merged = current.model_dump()
    merged.update(updates)

    record = _build(
        record_id=current.id,
        member_id=current.memberId,
        activity=merged["activity"],
        duration_sec=merged["durationSec"],
        distance_km=merged.get("distanceKm"),
        intensity=merged.get("intensity"),
        subjective=merged.get("subjective"),
        notes=merged.get("notes") or "",
        start_at=merged["startAt"],
        source=merged["source"],
        timezone=timezone,
        created_at=current.createdAt,
        updated_at=utc_now(),
    )
    update_record_row(session, row, record)
    return _to_exercise(row)


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT, summary="软删除运动记录")
def delete_exercise(exercise_id: str, session: SessionDep) -> Response:
    row = _require_exercise(session, exercise_id)
    current = record_from_row(row)
    now = utc_now()
    merged = current.model_dump(by_alias=True, mode="json")
    merged["deletedAt"] = now
    merged["updatedAt"] = now
    update_record_row(session, row, HealthRecord.model_validate(merged))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

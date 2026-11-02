"""记录与信号 API。

分页约定：``limit`` + ``offset``（默认 50 / 0，最大 500），按 ``capturedAt`` 倒序，
响应体包含 ``items/total/limit/offset``。软删除的记录默认不可见。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, Header, Query, Response, status
from fastapi.encoders import jsonable_encoder
from numpy.typing import NDArray
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import analysis_repo
from ..db.models import AnalysisTable, RecordTable
from ..db.repositories import (
    add_record,
    add_signal,
    get_member_row,
    get_record_row,
    get_signal_row,
    list_signal_rows,
    make_signal,
    record_from_row,
    signal_from_row,
    update_record_row,
)
from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import InvalidInputError, not_found
from ..domain.ids import new_id
from ..domain.models import (
    HealthRecord,
    RecordCreate,
    RecordUpdate,
    Signal,
    SignalInput,
)
from ..settings import get_settings
from ..storage.files import (
    decode_float32,
    delete_signal,
    read_import_file,
    read_signal,
    write_signal,
)
from .deps import SessionDep

router = APIRouter()

logger = logging.getLogger(__name__)


LatestAnalysisStatus = Literal["none", "queued", "running", "completed", "failed"]

_STATUS_TO_LATEST: dict[str, LatestAnalysisStatus] = {
    "queued": "queued",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    # 取消不是成功终态；列表按失败呈现，让用户知道需要重新分析。
    "cancelled": "failed",
}


class RecordListItem(HealthRecord):
    """列表项：附带最新分析状态，避免前端逐条查询（B3-02）。

    单条 ``GET /records/{id}`` 仍返回 ``HealthRecord``，形状不变。
    """

    latestAnalysisStatus: LatestAnalysisStatus = "none"
    latestAnalysisId: str | None = None
    latestAnalyzedAt: datetime | None = None


class RecordPage(BaseModel):
    items: list[RecordListItem]
    total: int
    limit: int
    offset: int


class CompareAnalysis(BaseModel):
    recordId: str
    latestCompleted: dict[str, Any] | None = None


class RecordComparePage(BaseModel):
    records: list[HealthRecord]
    analyses: list[CompareAnalysis]


@dataclass(frozen=True)
class _LatestAnalysis:
    analysis_id: str
    status: str
    created_at: datetime


def _latest_analysis_map(
    session: Session,
    record_ids: list[str],
    *,
    statuses: tuple[str, ...] | None = None,
) -> dict[str, _LatestAnalysis]:
    """一条窗口函数查询取出每条记录最新一次分析（可按状态过滤）。"""
    if not record_ids:
        return {}
    rank = func.row_number().over(
        partition_by=AnalysisTable.record_id,
        order_by=(AnalysisTable.created_at.desc(), AnalysisTable.id.desc()),
    )
    ranked = select(
        AnalysisTable.record_id,
        AnalysisTable.id,
        AnalysisTable.status,
        AnalysisTable.created_at,
        rank.label("rn"),
    ).where(AnalysisTable.record_id.in_(record_ids))
    if statuses is not None:
        ranked = ranked.where(AnalysisTable.status.in_(statuses))
    subquery = ranked.subquery()
    statement = select(
        subquery.c.record_id,
        subquery.c.id,
        subquery.c.status,
        subquery.c.created_at,
    ).where(subquery.c.rn == 1)
    return {
        row.record_id: _LatestAnalysis(row.id, row.status, row.created_at)
        for row in session.execute(statement).all()
    }


def _list_item(row: RecordTable, latest: _LatestAnalysis | None) -> RecordListItem:
    record = record_from_row(row)
    status_value: LatestAnalysisStatus = "none"
    analysis_id: str | None = None
    analyzed_at: datetime | None = None
    if latest is not None:
        status_value = _STATUS_TO_LATEST.get(latest.status, "failed")
        analysis_id = latest.analysis_id
        if status_value == "completed":
            analyzed_at = latest.created_at
    return RecordListItem.model_validate(
        {
            **record.model_dump(by_alias=True),
            "latestAnalysisStatus": status_value,
            "latestAnalysisId": analysis_id,
            "latestAnalyzedAt": analyzed_at,
        }
    )


def _validation_details(exc: PydanticValidationError) -> list[Any]:
    return jsonable_encoder(exc.errors(), custom_encoder={Exception: str})


def _load_signal_samples(signal: SignalInput) -> NDArray[np.float32]:
    settings = get_settings()
    if signal.fileRef is not None:
        raw = read_import_file(signal.fileRef)
        if len(raw) == 0:
            raise InvalidInputError("signal file is empty", code="empty_signal")
        if len(raw) % 4 != 0:
            raise InvalidInputError(
                "float32 fileRef must be a multiple of 4 bytes",
                code="invalid_signal_file",
                details={"bytes": len(raw)},
            )
        return decode_float32(raw)

    samples = signal.samples or []
    if not samples:
        raise InvalidInputError("signal samples must not be empty", code="empty_signal")
    if len(samples) > settings.signal_inline_max_samples:
        raise InvalidInputError(
            "too many inline samples; use fileRef or split the recording",
            code="signal_too_many_samples",
            details={"count": len(samples), "limit": settings.signal_inline_max_samples},
        )
    return np.asarray(samples, dtype="<f4")


def _resolve_signal_params(
    payload: RecordCreate, samples: NDArray[np.float32]
) -> tuple[float, str, list[str], float]:
    signal = payload.signal
    assert signal is not None  # 调用方已保证

    fs = signal.fs if signal.fs is not None else payload.samplingRate
    if fs is None:
        raise InvalidInputError(
            "sampling rate is required when writing a signal", code="sampling_rate_required"
        )
    if (
        signal.fs is not None
        and payload.samplingRate is not None
        and abs(signal.fs - payload.samplingRate) > 1e-9
    ):
        raise InvalidInputError(
            "signal.fs and samplingRate disagree",
            code="sampling_rate_conflict",
            details={"signalFs": signal.fs, "samplingRate": payload.samplingRate},
        )

    unit = payload.unit
    if signal.unit is not None:
        if payload.unit != "mV" and payload.unit != signal.unit:
            raise InvalidInputError(
                "signal.unit and unit disagree",
                code="unit_conflict",
                details={"signalUnit": signal.unit, "unit": payload.unit},
            )
        unit = signal.unit

    if payload.leads and signal.lead not in payload.leads:
        raise InvalidInputError(
            "signal lead is not listed in leads",
            code="lead_conflict",
            details={"lead": signal.lead, "leads": payload.leads},
        )
    leads = payload.leads or [signal.lead]

    duration = payload.durationSec
    if duration is None:
        duration = len(samples) / fs
    return fs, unit, leads, duration


def _require_record(session: Session, record_id: str) -> RecordTable:
    row = get_record_row(session, record_id)
    if row is None or row.deleted_at is not None:
        raise not_found("record", record_id)
    return row


def _as_storage_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return to_storage_dt(value)


@router.get("", response_model=RecordPage, summary="分页列出健康记录")
def list_records(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    member_id: Annotated[str | None, Query(alias="memberId")] = None,
    record_type: Annotated[str | None, Query(alias="recordType")] = None,
    record_type_prefix: Annotated[str | None, Query(alias="recordTypePrefix")] = None,
    module_id: Annotated[str | None, Query(alias="moduleId")] = None,
    captured_from: Annotated[datetime | None, Query(alias="capturedFrom")] = None,
    captured_to: Annotated[datetime | None, Query(alias="capturedTo")] = None,
    favorite: Annotated[bool | None, Query()] = None,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
) -> RecordPage:
    # 前缀过滤用于「健康数据」页一次性取出 org.eclipsehealth.health.*；
    # 与精确 recordType 同时给出会让结果含义不明确，直接拒绝。
    if record_type and record_type_prefix:
        raise InvalidInputError(
            "recordType and recordTypePrefix are mutually exclusive",
            code="invalid_query",
            details={"recordType": record_type, "recordTypePrefix": record_type_prefix},
        )

    conditions = []
    if not include_deleted:
        conditions.append(RecordTable.deleted_at.is_(None))
    if member_id:
        conditions.append(RecordTable.member_id == member_id)
    if record_type:
        conditions.append(RecordTable.record_type == record_type)
    if record_type_prefix:
        conditions.append(RecordTable.record_type.startswith(record_type_prefix))
    if module_id:
        conditions.append(RecordTable.module_id == module_id)
    if favorite is not None:
        # 旧记录的 data JSON 没有 favorite 键；json_extract 返回 NULL，
        # coalesce 成 0 让它们落在「未收藏」一侧。
        flag = func.coalesce(func.json_extract(RecordTable.data, "$.favorite"), 0)
        conditions.append(flag == (1 if favorite else 0))
    since = _as_storage_datetime(captured_from)
    until = _as_storage_datetime(captured_to)
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
    rows = list(session.exec(statement))
    latest_map = _latest_analysis_map(session, [row.id for row in rows])
    return RecordPage(
        items=[_list_item(row, latest_map.get(row.id)) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/compare",
    response_model=RecordComparePage,
    summary="对比 2–4 条记录的最新完成分析",
)
def compare_records(
    session: SessionDep,
    ids: Annotated[str, Query(description="逗号分隔的记录 ID，2–4 条")],
) -> RecordComparePage:
    requested = [part.strip() for part in ids.split(",") if part.strip()]
    unique = list(dict.fromkeys(requested))
    if len(requested) != len(unique) or not 2 <= len(unique) <= 4:
        raise InvalidInputError(
            "ids must contain 2 to 4 distinct record ids",
            code="invalid_ids",
            details={"ids": requested, "count": len(unique)},
        )

    rows = {
        row.id: row
        for row in session.exec(select(RecordTable).where(RecordTable.id.in_(unique)))
    }
    records: list[HealthRecord] = []
    for record_id in unique:
        row = rows.get(record_id)
        if row is None or row.deleted_at is not None:
            raise not_found("record", record_id)
        records.append(record_from_row(row))

    latest = _latest_analysis_map(session, unique, statuses=("completed",))
    analyses: list[CompareAnalysis] = []
    for record_id in unique:
        entry = latest.get(record_id)
        latest_completed: dict[str, Any] | None = None
        if entry is not None:
            analysis_row = analysis_repo.get_analysis_row(session, entry.analysis_id)
            if analysis_row is not None:
                latest_completed = analysis_repo.summary_of(analysis_row)
                latest_completed["measurements"] = analysis_repo.measurements_for(
                    session, analysis_row.id
                )
        analyses.append(
            CompareAnalysis(recordId=record_id, latestCompleted=latest_completed)
        )
    return RecordComparePage(records=records, analyses=analyses)


@router.post("", response_model=HealthRecord, status_code=status.HTTP_201_CREATED)
def create_record(payload: RecordCreate, session: SessionDep) -> HealthRecord:
    if get_member_row(session, payload.memberId) is None:
        raise not_found("member", payload.memberId)
    if payload.signal is None and payload.signalIds:
        raise InvalidInputError(
            "signalIds are assigned by the server when a signal is provided",
            code="signal_ids_not_supported",
        )

    now = utc_now()
    record_id = new_id("record")
    signal: Signal | None = None
    written_paths: list[str] = []

    if payload.signal is not None:
        samples = _load_signal_samples(payload.signal)
        fs, unit, leads, duration = _resolve_signal_params(payload, samples)
        signal_id = new_id("signal")
        relative_path, digest, _size = write_signal(signal_id, samples)
        written_paths.append(relative_path)
        signal = make_signal(
            signal_id=signal_id,
            record_id=record_id,
            lead=payload.signal.lead,
            fs=fs,
            unit=unit,
            n_samples=int(samples.size),
            relative_path=relative_path,
            sha256=digest,
            created_at=now,
        )
    else:
        fs, unit, leads, duration = (
            payload.samplingRate,
            payload.unit,
            payload.leads,
            payload.durationSec,
        )

    try:
        record = HealthRecord(
            id=record_id,
            memberId=payload.memberId,
            recordType=payload.recordType,
            moduleId=payload.moduleId,
            capturedAt=payload.capturedAt,
            timezone=payload.timezone,
            source=payload.source,
            samplingRate=fs,
            leads=leads,
            durationSec=duration,
            unit=unit,
            signalIds=[signal.id] if signal is not None else [],
            quality=payload.quality,
            tags=payload.tags,
            notes=payload.notes,
            metadata=payload.metadata,
            payload=payload.payload,
            provenance=payload.provenance,
            createdAt=now,
            updatedAt=now,
        )
    except PydanticValidationError as exc:
        for path in written_paths:
            delete_signal(path)
        raise InvalidInputError(
            "record validation failed",
            code="record_invalid",
            details=_validation_details(exc),
        ) from exc

    try:
        add_record(session, record, commit=False)
        if signal is not None:
            add_signal(session, signal, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        for path in written_paths:
            delete_signal(path)
        raise

    return record


@router.get("/{record_id}", response_model=HealthRecord, summary="按 ID 读取记录")
def get_record(record_id: str, session: SessionDep) -> HealthRecord:
    return record_from_row(_require_record(session, record_id))


@router.patch("/{record_id}", response_model=HealthRecord, summary="更新记录（标签/备注/元数据等）")
def patch_record(
    record_id: str, payload: RecordUpdate, session: SessionDep
) -> HealthRecord:
    row = _require_record(session, record_id)
    current = record_from_row(row)
    merged = current.model_dump(by_alias=True, mode="json")
    merged.update(payload.model_dump(exclude_unset=True, by_alias=True, mode="json"))
    merged["updatedAt"] = utc_now()
    try:
        updated = HealthRecord.model_validate(merged)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "record validation failed",
            code="record_invalid",
            details=_validation_details(exc),
        ) from exc
    return update_record_row(session, row, updated)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, summary="软删除记录")
def delete_record(record_id: str, session: SessionDep) -> Response:
    row = _require_record(session, record_id)
    # 先取消进行中的分析：否则 running 行会继续占用串行队列，且旧任务复用逻辑
    # 会让用户以为「删了记录/分析仍然卡住」。取消失败不应阻止删除。
    try:
        from ..analysis_service import get_analysis_service

        get_analysis_service().cancel_record(record_id)
    except Exception:
        logger.debug("cancel active analyses on record delete failed", exc_info=True)
    current = record_from_row(row)
    now = utc_now()
    merged = current.model_dump(by_alias=True, mode="json")
    merged["deletedAt"] = now
    merged["updatedAt"] = now
    update_record_row(session, row, HealthRecord.model_validate(merged))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{record_id}/signals", response_model=list[Signal], summary="列出记录的信号元数据")
def list_record_signals(record_id: str, session: SessionDep) -> list[Signal]:
    _require_record(session, record_id)
    return [signal_from_row(row) for row in list_signal_rows(session, record_id)]


@router.get(
    "/{record_id}/signal",
    summary="读取原始 float32 波形",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def get_record_signal(
    record_id: str,
    session: SessionDep,
    lead: Annotated[str | None, Query(max_length=16)] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    _require_record(session, record_id)
    if lead is None:
        rows = list_signal_rows(session, record_id)
        if not rows:
            raise not_found("signal", record_id)
        if len(rows) > 1:
            raise InvalidInputError(
                "lead is required when the record has multiple signals",
                code="lead_required",
                details={"leads": [row.lead for row in rows]},
            )
        row = rows[0]
    else:
        row = get_signal_row(session, record_id, lead)
        if row is None:
            raise not_found("signal", f"{record_id}/{lead}")

    etag = f'"{row.sha256}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    data = read_signal(row.relative_path, row.sha256)
    headers = {
        "ETag": etag,
        "Content-Disposition": f'attachment; filename="{row.id}.f32"',
        "X-Signal-Id": row.id,
        "X-Signal-Lead": row.lead,
        "X-Signal-Fs": f"{row.fs:g}",
        "X-Signal-Unit": row.unit,
        "X-Signal-Samples": str(row.n_samples),
        "X-Signal-Sha256": row.sha256,
    }
    return Response(content=data, media_type="application/octet-stream", headers=headers)


__all__ = ["router"]

"""对外 API（F3）：密钥管理、只读 REST、健康数据写入、OpenAI 兼容端点。

设计边界：

- 仅本机回环可访问；外部客户端必须携带 ``Authorization: Bearer`` 或 ``X-API-Key``；
- 读取只返回摘要与测量值，绝不返回波形、备注、成员姓名与 metadata；
- 默认操作「本人」成员，与应用内助手看到的数据范围一致；
- 审计只记录 keyId / action / 成败，不记录任何健康数据内容。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from .. import external_auth
from ..db import analysis_repo
from ..db.base import engine, session_scope
from ..db.models import RecordTable
from ..db.repositories import (
    add_record,
    ensure_default_member,
    get_record_row,
)
from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import ApiError, InvalidInputError, not_found
from ..domain.ids import new_id, uuid7
from ..domain.models import HealthRecord, SourceInfo
from ..llm import agent
from ..llm.providers import Provider, ProviderError, get_provider_store
from ..llm.tools import ToolBox
from ..metrics.models import METRIC_RECORD_TYPE
from .deps import SessionDep

logger = logging.getLogger(__name__)

HEALTH_PREFIX = "org.eclipsehealth.health."
ECG_RECORD_TYPE = "org.eclipsehealth.ecg"
OPENAI_MODEL_ID = "eclipse-health"

HealthKind = Literal["steps", "heart-rate", "sleep", "body-mass", "blood-pressure"]
LOCAL_HOSTS = frozenset(
    {"127.0.0.1", "::1", "localhost", "testclient", "::ffff:127.0.0.1"}
)
DEFAULT_UNITS: dict[str, str] = {
    "steps": "count",
    "heart-rate": "count/min",
    "sleep": "min",
    "body-mass": "kg",
    "blood-pressure": "mmHg",
}


# --------------------------------------------------------------------------- #
# 本机限制与 key 认证
# --------------------------------------------------------------------------- #


def _require_local(request: Request) -> None:
    """服务本身只监听 127.0.0.1；这里再拒绝非回环来源作为纵深防御。"""
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise ApiError(
            "external API is only available on localhost",
            code="local_only",
            status_code=403,
        )


def _key_dependency(scope: str) -> Any:
    def dependency(
        session: SessionDep,
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> external_auth.ExternalKey:
        token = external_auth.extract_token(authorization, x_api_key)
        if not token:
            raise external_auth.InvalidApiKeyError("missing API key")
        key = external_auth.authenticate(session, token)
        external_auth.require_scope(key, scope)
        return key

    return dependency


require_read = _key_dependency("read")
require_write = _key_dependency("write")
require_assistant = _key_dependency("assistant")

router = APIRouter(
    prefix="/external",
    tags=["external"],
    dependencies=[Depends(_require_local)],
)


def _audit_call(
    session: Session | None,
    *,
    key_id: str,
    action: str,
    ok: bool,
    error: str | None = None,
) -> None:
    """写 ``external.call``；审计失败不能影响主请求。"""
    detail: dict[str, Any] = {"keyId": key_id, "action": action, "ok": ok}
    if error:
        detail["error"] = error
    try:
        from ..modules import audit

        if session is not None:
            audit.append(session, "external.call", scope=action, detail=detail)
            session.commit()
            return
        with session_scope() as db:
            audit.append(db, "external.call", scope=action, detail=detail)
    except Exception:
        logger.warning("external audit append failed action=%s", action, exc_info=True)
        if session is not None:
            session.rollback()


# --------------------------------------------------------------------------- #
# 密钥管理（本地设置用，不要求 key 认证）
# --------------------------------------------------------------------------- #


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=3)


@router.get("/keys", summary="列出对外 API Key（masked）")
def list_api_keys(session: SessionDep) -> dict[str, Any]:
    items = [external_auth.key_to_dict(row) for row in external_auth.list_keys(session)]
    return {"items": items}


@router.post("/keys", status_code=201, summary="创建 API Key（明文 token 仅返回一次）")
def create_api_key(payload: KeyCreate, session: SessionDep) -> dict[str, Any]:
    row, token = external_auth.create_key(
        session, name=payload.name, scopes=payload.scopes
    )
    data = external_auth.key_to_dict(row)
    data["token"] = token
    return data


@router.delete("/keys/{key_id}", status_code=204, summary="撤销 API Key")
def revoke_api_key(key_id: str, session: SessionDep) -> Response:
    row = external_auth.revoke_key(session, key_id)
    if row is None:
        raise not_found("api_key", key_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# 记录 / 分析读取
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _health_kind(record_type: str) -> str | None:
    return record_type[len(HEALTH_PREFIX) :] if record_type.startswith(HEALTH_PREFIX) else None


def _record_kind(record_type: str) -> str:
    health = _health_kind(record_type)
    if health:
        return health
    if record_type == ECG_RECORD_TYPE:
        return "ecg"
    if record_type == METRIC_RECORD_TYPE:
        return "metric"
    return "other"


def _source_view(data: dict[str, Any]) -> dict[str, Any]:
    source = data.get("source")
    if not isinstance(source, dict):
        return {}
    return {
        key: source[key]
        for key in ("kind", "manufacturer", "device", "app")
        if source.get(key) is not None
    }


def _quality_view(data: dict[str, Any]) -> dict[str, Any] | None:
    quality = data.get("quality")
    if not isinstance(quality, dict):
        return None
    view = {"score": quality.get("score"), "level": quality.get("level")}
    return view if view["score"] is not None or view["level"] is not None else None


def _record_summary(row: RecordTable) -> dict[str, Any]:
    data = row.data or {}
    kind = _record_kind(row.record_type)
    summary: dict[str, Any] = {
        "id": row.id,
        "recordType": row.record_type,
        "kind": kind,
        "capturedAt": data.get("capturedAt"),
        "timezone": data.get("timezone"),
        "source": _source_view(data),
        "samplingRate": data.get("samplingRate"),
        "leads": list(data.get("leads") or []),
        "durationSec": data.get("durationSec"),
        "unit": data.get("unit"),
        "quality": _quality_view(data),
        "tagCount": len(data.get("tags") or []),
        "favorite": bool(data.get("favorite")),
        "signalCount": len(data.get("signalIds") or []),
    }
    if kind in {"body-mass", "blood-pressure", "steps", "heart-rate", "sleep"}:
        summary["value"] = (row.payload or {}).get("value")
    elif kind == "metric":
        summary["value"] = (row.payload or {}).get("values")
    return summary


def _require_record(session: Session, record_id: str, member_id: str) -> RecordTable:
    row = get_record_row(session, record_id)
    if row is None or row.deleted_at is not None or row.member_id != member_id:
        raise not_found("record", record_id)
    return row


@router.get("/records", summary="记录摘要列表（不含波形/备注/成员姓名）")
def list_records(
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    recordTypePrefix: Annotated[str | None, Query(max_length=128)] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    conditions: list[Any] = [
        RecordTable.member_id == member_id,
        RecordTable.deleted_at.is_(None),
    ]
    if recordTypePrefix:
        conditions.append(RecordTable.record_type.startswith(recordTypePrefix))
    since = _as_utc(from_)
    until = _as_utc(to)
    if since is not None:
        conditions.append(RecordTable.captured_at >= to_storage_dt(since))
    if until is not None:
        conditions.append(RecordTable.captured_at <= to_storage_dt(until))

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
    items = [_record_summary(row) for row in session.exec(statement)]
    _audit_call(session, key_id=key.id, action="records.list", ok=True)
    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.get("/records/{record_id}", summary="单条记录摘要；健康数据附带 payload")
def get_record(
    record_id: str,
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_read)],
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    row = _require_record(session, record_id, member_id)
    payload: dict[str, Any] | None = None
    kind = _health_kind(row.record_type)
    if kind:
        raw = row.payload or {}
        payload = {
            "kind": kind,
            "value": raw.get("value"),
            "unit": raw.get("unit"),
            "startAt": raw.get("startAt"),
            "endAt": raw.get("endAt"),
            "sourceApp": raw.get("sourceApp"),
        }
    summary = _record_summary(row)
    _audit_call(session, key_id=key.id, action="records.get", ok=True)
    return {"record": summary, "payload": payload}


def _measurement_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "code",
            "label",
            "value",
            "unit",
            "ucum",
            "confidence",
            "method",
            "warnings",
        )
        if key in item
    }


@router.get("/analyses/{analysis_id}", summary="分析摘要 + 测量值（不含逐搏/波形）")
def get_analysis(
    analysis_id: str,
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_read)],
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    row = analysis_repo.get_analysis_row(session, analysis_id)
    if row is None:
        raise not_found("analysis", analysis_id)
    record = get_record_row(session, row.record_id)
    if record is None or record.deleted_at is not None or record.member_id != member_id:
        raise not_found("analysis", analysis_id)
    summary = analysis_repo.summary_of(row)
    summary.pop("parameters", None)
    summary.pop("provenance", None)
    measurements = [
        _measurement_view(item)
        for item in analysis_repo.measurements_for(session, row.id)
        if isinstance(item, dict)
    ]
    _audit_call(session, key_id=key.id, action="analyses.get", ok=True)
    return {"analysis": summary, "measurements": measurements}


# --------------------------------------------------------------------------- #
# 健康数据
# --------------------------------------------------------------------------- #


def _metric_health_item(row: RecordTable) -> dict[str, Any] | None:
    payload = row.payload or {}
    kind = payload.get("kind")
    values = payload.get("values") or {}
    if not isinstance(values, dict):
        return None
    data = row.data or {}
    if kind == "weight":
        health_kind = "body-mass"
        value: Any = values.get("weight")
    elif kind == "blood_pressure":
        health_kind = "blood-pressure"
        value = {
            "systolic": values.get("systolic"),
            "diastolic": values.get("diastolic"),
        }
    else:
        return None
    return {
        "id": row.id,
        "recordType": row.record_type,
        "kind": health_kind,
        "capturedAt": data.get("capturedAt"),
        "value": value,
        "unit": data.get("unit") or DEFAULT_UNITS[health_kind],
        "startAt": data.get("capturedAt"),
        "endAt": data.get("capturedAt"),
        "durationSec": data.get("durationSec"),
        "sourceApp": None,
    }


def _health_item(row: RecordTable) -> dict[str, Any] | None:
    if row.record_type == METRIC_RECORD_TYPE:
        return _metric_health_item(row)
    if not row.record_type.startswith(HEALTH_PREFIX):
        return None
    payload = row.payload or {}
    data = row.data or {}
    return {
        "id": row.id,
        "recordType": row.record_type,
        "kind": row.record_type[len(HEALTH_PREFIX) :],
        "capturedAt": data.get("capturedAt"),
        "value": payload.get("value"),
        "unit": payload.get("unit") or data.get("unit"),
        "startAt": payload.get("startAt") or data.get("capturedAt"),
        "endAt": payload.get("endAt") or data.get("capturedAt"),
        "durationSec": data.get("durationSec"),
        "sourceApp": payload.get("sourceApp"),
    }


def _health_conditions(kind: str | None) -> list[Any]:
    metric_kind = RecordTable.payload["kind"].as_string()
    if kind in {"steps", "heart-rate", "sleep"}:
        return [RecordTable.record_type == f"{HEALTH_PREFIX}{kind}"]
    if kind == "body-mass":
        return [
            or_(
                RecordTable.record_type == f"{HEALTH_PREFIX}body-mass",
                and_(RecordTable.record_type == METRIC_RECORD_TYPE, metric_kind == "weight"),
            )
        ]
    if kind == "blood-pressure":
        return [
            or_(
                RecordTable.record_type == f"{HEALTH_PREFIX}blood-pressure",
                and_(
                    RecordTable.record_type == METRIC_RECORD_TYPE,
                    metric_kind == "blood_pressure",
                ),
            )
        ]
    return [
        or_(
            RecordTable.record_type.startswith(HEALTH_PREFIX),
            and_(
                RecordTable.record_type == METRIC_RECORD_TYPE,
                or_(metric_kind == "weight", metric_kind == "blood_pressure"),
            ),
        )
    ]


@router.get("/health-data", summary="健康数据列表（步数/心率/睡眠/体重/血压）")
def list_health_data(
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_read)],
    kind: Annotated[HealthKind | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    conditions: list[Any] = [
        RecordTable.member_id == member_id,
        RecordTable.deleted_at.is_(None),
        *_health_conditions(kind),
    ]
    since = _as_utc(from_)
    until = _as_utc(to)
    if since is not None:
        conditions.append(RecordTable.captured_at >= to_storage_dt(since))
    if until is not None:
        conditions.append(RecordTable.captured_at <= to_storage_dt(until))

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
    items = [item for row in session.exec(statement) if (item := _health_item(row))]
    _audit_call(session, key_id=key.id, action="health-data.list", ok=True)
    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


# --------------------------------------------------------------------------- #
# 聚合摘要
# --------------------------------------------------------------------------- #


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _stat(values: list[float], unit: str) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "latest": round(values[0], 2),
        "mean": round(sum(values) / len(values), 2),
        "unit": unit,
        "count": len(values),
    }


def _blood_pressure_stat(values: list[tuple[float, float]]) -> dict[str, Any] | None:
    if not values:
        return None
    systolic = [item[0] for item in values]
    diastolic = [item[1] for item in values]
    return {
        "latest": {
            "systolic": round(systolic[0], 1),
            "diastolic": round(diastolic[0], 1),
        },
        "mean": {
            "systolic": round(sum(systolic) / len(systolic), 2),
            "diastolic": round(sum(diastolic) / len(diastolic), 2),
        },
        "unit": "mmHg",
        "count": len(values),
    }


@router.get("/summary", summary="最近 N 天的记录与健康数据聚合")
def get_summary(
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_read)],
    days: Annotated[int, Query(ge=1, le=365)] = 7,
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    until = utc_now()
    since = until - timedelta(days=days)
    since_storage = to_storage_dt(since)

    ecg_rows = list(
        session.exec(
            select(RecordTable)
            .where(
                RecordTable.member_id == member_id,
                RecordTable.deleted_at.is_(None),
                RecordTable.record_type == ECG_RECORD_TYPE,
                RecordTable.captured_at >= since_storage,
            )
            .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
        )
    )

    heart_rate: list[float] = []
    hrv: list[float] = []
    quality: list[float] = []
    latest_level: str | None = None
    analysis_count = 0
    for row in ecg_rows:
        data = row.data or {}
        quality_view = data.get("quality") if isinstance(data.get("quality"), dict) else {}
        score = _numeric(quality_view.get("score"))
        if score is not None:
            quality.append(score)
            if latest_level is None:
                level = quality_view.get("level")
                latest_level = level if isinstance(level, str) else None
        latest = analysis_repo.latest_row(session, row.id)
        if latest is None or latest.status != "completed":
            continue
        analysis_count += 1
        measurements = {
            str(item.get("code")): item
            for item in analysis_repo.measurements_for(session, latest.id)
            if isinstance(item, dict)
        }
        hr = _numeric((measurements.get("heart_rate_mean") or {}).get("value"))
        if hr is not None:
            heart_rate.append(hr)
        rmssd = _numeric((measurements.get("rmssd") or {}).get("value"))
        if rmssd is not None:
            hrv.append(rmssd)

    health_rows = list(
        session.exec(
            select(RecordTable)
            .where(
                RecordTable.member_id == member_id,
                RecordTable.deleted_at.is_(None),
                RecordTable.captured_at >= since_storage,
                *_health_conditions(None),
            )
            .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
        )
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in health_rows:
        item = _health_item(row)
        if item is not None:
            grouped.setdefault(item["kind"], []).append(item)

    steps = [
        value
        for item in grouped.get("steps", [])
        if (value := _numeric(item.get("value"))) is not None
    ]
    heart_rate_data = [
        value
        for item in grouped.get("heart-rate", [])
        if (value := _numeric(item.get("value"))) is not None
    ]
    heart_rate.extend(heart_rate_data)
    weights = [
        value
        for item in grouped.get("body-mass", [])
        if (value := _numeric(item.get("value"))) is not None
    ]
    sleep_minutes = [
        duration / 60.0
        for item in grouped.get("sleep", [])
        if (duration := _numeric(item.get("durationSec"))) is not None and duration > 0
    ]
    blood_pressure: list[tuple[float, float]] = []
    for item in grouped.get("blood-pressure", []):
        value = item.get("value")
        if not isinstance(value, dict):
            continue
        systolic = _numeric(value.get("systolic"))
        diastolic = _numeric(value.get("diastolic"))
        if systolic is not None and diastolic is not None:
            blood_pressure.append((systolic, diastolic))

    quality_stat: dict[str, Any] | None = None
    if quality:
        quality_stat = {
            "latest": round(quality[0], 3),
            "mean": round(sum(quality) / len(quality), 3),
            "level": latest_level,
            "count": len(quality),
        }

    _audit_call(session, key_id=key.id, action="summary.get", ok=True)
    return {
        "days": days,
        "from": _iso(since),
        "to": _iso(until),
        "recordCount": len(ecg_rows),
        "healthRecordCount": len(health_rows),
        "analysisCount": analysis_count,
        "heartRate": _stat(heart_rate, "bpm"),
        "hrv": _stat(hrv, "ms"),
        "quality": quality_stat,
        "steps": _stat(steps, "count"),
        "sleep": _stat(sleep_minutes, "min"),
        "weight": _stat(weights, "kg"),
        "bloodPressure": _blood_pressure_stat(blood_pressure),
    }


# --------------------------------------------------------------------------- #
# 写入健康数据
# --------------------------------------------------------------------------- #


class HealthDataCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: HealthKind
    value: float | str | dict[str, float]
    unit: str | None = Field(default=None, max_length=32)
    startAt: AwareDatetime
    endAt: AwareDatetime | None = None
    sourceApp: str | None = Field(default=None, max_length=64)


def _tidy(value: float) -> float:
    return int(value) if float(value).is_integer() else round(float(value), 3)


def _invalid(message: str, code: str = "invalid_value") -> InvalidInputError:
    return InvalidInputError(message, code=code)


def _build_health_record(
    payload: HealthDataCreate, *, member_id: str, now: datetime
) -> HealthRecord:
    start = payload.startAt.astimezone(UTC)
    end = payload.endAt.astimezone(UTC) if payload.endAt is not None else None
    if end is not None and end < start:
        raise _invalid("endAt must not be earlier than startAt", "invalid_time_range")

    kind = payload.kind
    unit = payload.unit or DEFAULT_UNITS[kind]
    duration: float | None = None
    value: Any = payload.value

    if kind == "steps":
        numeric = _numeric(payload.value)
        if numeric is None or not 0 <= numeric <= 10_000_000:
            raise _invalid("steps value must be a number between 0 and 10000000")
        value = _tidy(numeric)
    elif kind == "heart-rate":
        numeric = _numeric(payload.value)
        if numeric is None or not 10 <= numeric <= 400:
            raise _invalid("heart-rate value must be between 10 and 400")
        value = _tidy(numeric)
    elif kind == "body-mass":
        numeric = _numeric(payload.value)
        if numeric is None or not 2 <= numeric <= 500:
            raise _invalid("body-mass value must be between 2 and 500 kg")
        value = _tidy(numeric)
    elif kind == "sleep":
        if isinstance(payload.value, str):
            category = payload.value.strip()
            if not category or len(category) > 64:
                raise _invalid("sleep category must be 1-64 characters")
            if end is None:
                raise _invalid("sleep category requires endAt", "invalid_time_range")
            duration = (end - start).total_seconds()
            value = category
            unit = "1"
        else:
            numeric = _numeric(payload.value)
            if numeric is None or not 0 <= numeric <= 24 * 60:
                raise _invalid("sleep value must be minutes between 0 and 1440")
            value = _tidy(numeric)
            duration = numeric * 60.0
            unit = payload.unit or "min"
    elif kind == "blood-pressure":
        if not isinstance(payload.value, dict):
            raise _invalid(
                "blood-pressure value must be {systolic, diastolic}",
                "invalid_blood_pressure",
            )
        systolic = _numeric(payload.value.get("systolic"))
        diastolic = _numeric(payload.value.get("diastolic"))
        if systolic is None or not 50 <= systolic <= 300:
            raise _invalid("systolic must be between 50 and 300", "invalid_blood_pressure")
        if diastolic is None or not 20 <= diastolic <= 200:
            raise _invalid("diastolic must be between 20 and 200", "invalid_blood_pressure")
        if (payload.unit or "mmHg") != "mmHg":
            raise _invalid("blood-pressure unit must be mmHg", "unsupported_unit")
        value = {"systolic": _tidy(systolic), "diastolic": _tidy(diastolic)}
        unit = "mmHg"

    if end is not None and duration is None:
        duration = (end - start).total_seconds()

    record_payload: dict[str, Any] = {
        "value": value,
        "unit": unit,
        "startAt": _iso(start),
        "endAt": _iso(end) if end is not None else _iso(start),
    }
    if payload.sourceApp:
        record_payload["sourceApp"] = payload.sourceApp

    try:
        return HealthRecord(
            id=new_id("record"),
            memberId=member_id,
            recordType=f"{HEALTH_PREFIX}{kind}",
            moduleId=None,
            capturedAt=start,
            timezone="UTC",
            source=SourceInfo(kind="manual", app=payload.sourceApp),
            samplingRate=None,
            leads=[],
            durationSec=duration,
            unit=unit,
            signalIds=[],
            tags=[],
            notes="",
            metadata={},
            payload=record_payload,
            createdAt=now,
            updatedAt=now,
        )
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "health record validation failed",
            code="invalid_health_record",
            details=jsonable_encoder(exc.errors(include_url=False), custom_encoder={Exception: str}),
        ) from exc


@router.post("/health-data", status_code=201, summary="写入健康数据（scope: write）")
def create_health_data(
    payload: HealthDataCreate,
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_write)],
) -> dict[str, Any]:
    member_id = ensure_default_member(session).id
    record = _build_health_record(payload, member_id=member_id, now=utc_now())
    add_record(session, record)
    row = get_record_row(session, record.id)
    assert row is not None  # 刚写入
    summary = _record_summary(row)
    _audit_call(session, key_id=key.id, action="health-data.write", ok=True)
    return {"record": summary}


# --------------------------------------------------------------------------- #
# OpenAI 兼容端点
# --------------------------------------------------------------------------- #


class OpenAIMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | None = None


class ChatCompletionIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = OPENAI_MODEL_ID
    messages: list[OpenAIMessage] = Field(min_length=1, max_length=100)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)


def _extract_messages(messages: list[OpenAIMessage]) -> tuple[str, list[dict[str, str]]]:
    """只接受 user/assistant 文本；system 与 tool 消息一律忽略，防止越权提示词。"""
    conversation: list[dict[str, str]] = []
    for message in messages:
        if message.role not in {"user", "assistant"}:
            continue
        content = (message.content or "").strip()
        if not content:
            continue
        if len(content) > 8_000:
            raise InvalidInputError(
                "message content exceeds 8000 characters", code="invalid_messages"
            )
        conversation.append({"role": message.role, "content": content})
    while conversation and conversation[-1]["role"] != "user":
        conversation.pop()
    if not conversation:
        raise InvalidInputError(
            "at least one non-empty user message is required", code="invalid_messages"
        )
    content = conversation[-1]["content"]
    history = conversation[:-1][-agent.MAX_HISTORY_MESSAGES :]
    return content, history


def _select_provider() -> tuple[Provider, str | None]:
    store = get_provider_store()
    for provider in store.list():
        if not provider.enabled:
            continue
        if provider.needs_key and not provider.key_ref:
            continue
        try:
            api_key = store.resolve_api_key(provider)
        except ProviderError:
            continue
        return provider, api_key
    raise ApiError(
        "LLM provider is not configured; configure one in app settings first",
        code="llm_not_configured",
        status_code=503,
    )


def _llm_api_error(exc: agent.LLMError) -> ApiError:
    if exc.code in {"missing_api_key", "key_unavailable"}:
        return ApiError(
            "LLM provider is not configured; configure one in app settings first",
            code="llm_not_configured",
            status_code=503,
        )
    return ApiError(exc.message, code="llm_error", status_code=502)


def _openai_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(usage.get("promptTokens") or 0),
        "completion_tokens": int(usage.get("completionTokens") or 0),
        "total_tokens": int(usage.get("totalTokens") or 0),
    }


def _openai_error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _prepare_chat(
    session: Session, payload: ChatCompletionIn
) -> tuple[Provider, str | None, str, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    if payload.model != OPENAI_MODEL_ID:
        raise ApiError(
            f"unknown model: {payload.model}",
            code="model_not_found",
            status_code=404,
            details={"supported": [OPENAI_MODEL_ID]},
        )
    content, history = _extract_messages(payload.messages)
    provider, api_key = _select_provider()
    member_id = ensure_default_member(session).id
    context = agent.build_context(
        session, member_id=member_id, record_id=None, include_notes=False
    )
    messages = agent.build_messages(
        context_text=context["contextText"],
        history=history,
        content=content,
        style="brief",
    )
    transparency = agent.build_transparency(
        provider, context=context, messages=messages
    )
    return provider, api_key, member_id, messages, transparency, context


async def _agent_events(
    *,
    provider: Provider,
    api_key: str | None,
    member_id: str,
    messages: list[dict[str, Any]],
    transparency: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """每次调用使用独立只读会话，避免流式响应期间依赖请求作用域会话。"""
    tool_session = Session(engine)
    try:
        toolbox = ToolBox(tool_session, member_id)
        adapter = agent.adapter_for(provider, api_key)
        async for event in agent.stream_reply(
            provider=provider,
            adapter=adapter,
            messages=messages,
            toolbox=toolbox,
            transparency=transparency,
            cancel=asyncio.Event(),
        ):
            yield event
    finally:
        tool_session.close()


def _chat_id() -> str:
    return f"chatcmpl-{uuid7().hex}"


@router.get("/openai/v1/models", summary="OpenAI 兼容：模型列表")
def list_openai_models(
    key: Annotated[external_auth.ExternalKey, Depends(require_assistant)],
) -> dict[str, Any]:
    _audit_call(None, key_id=key.id, action="openai.models", ok=True)
    return {
        "object": "list",
        "data": [
            {
                "id": OPENAI_MODEL_ID,
                "object": "model",
                "created": 1_700_000_000,
                "owned_by": "eclipse-health",
            }
        ],
    }


@router.post("/openai/v1/chat/completions", summary="OpenAI 兼容：对话补全")
async def chat_completions(
    payload: ChatCompletionIn,
    session: SessionDep,
    key: Annotated[external_auth.ExternalKey, Depends(require_assistant)],
) -> Any:
    provider, api_key, member_id, messages, transparency, _context = _prepare_chat(
        session, payload
    )
    chat_id = _chat_id()
    created = int(utc_now().timestamp())

    if payload.stream:
        return StreamingResponse(
            _stream_completion(
                key_id=key.id,
                chat_id=chat_id,
                created=created,
                provider=provider,
                api_key=api_key,
                member_id=member_id,
                messages=messages,
                transparency=transparency,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    parts: list[str] = []
    final: dict[str, Any] | None = None
    try:
        async for event in _agent_events(
            provider=provider,
            api_key=api_key,
            member_id=member_id,
            messages=messages,
            transparency=transparency,
        ):
            if event["event"] == "token":
                parts.append(str(event["data"].get("text") or ""))
            elif event["event"] == "done":
                final = event["data"]
    except agent.LLMError as exc:
        _audit_call(
            session, key_id=key.id, action="openai.chat", ok=False, error=exc.code
        )
        raise _llm_api_error(exc) from exc
    except agent.TurnTimeout as exc:
        _audit_call(
            session, key_id=key.id, action="openai.chat", ok=False, error="timeout"
        )
        raise ApiError("assistant turn timed out", code="timeout", status_code=504) from exc

    content = (final or {}).get("content") or "".join(parts)
    citations = (final or {}).get("citations") or []
    _audit_call(session, key_id=key.id, action="openai.chat", ok=True)
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created,
        "model": OPENAI_MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": _openai_usage((final or {}).get("usage")),
        # 非标准字段：工具引用，供外部 UI 显示来源。
        "citations": citations,
    }


def _chunk(
    *,
    chat_id: str,
    created: int,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> str:
    body: dict[str, Any] = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": OPENAI_MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        body["usage"] = usage
    if citations is not None:
        body["citations"] = citations
    return f"data: {json.dumps(body, ensure_ascii=False, default=str)}\n\n"


async def _stream_completion(
    *,
    key_id: str,
    chat_id: str,
    created: int,
    provider: Provider,
    api_key: str | None,
    member_id: str,
    messages: list[dict[str, Any]],
    transparency: dict[str, Any],
) -> AsyncIterator[str]:
    parts: list[str] = []
    final: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    emitted = False
    yield _chunk(
        chat_id=chat_id, created=created, delta={"role": "assistant", "content": ""}
    )
    try:
        async for event in _agent_events(
            provider=provider,
            api_key=api_key,
            member_id=member_id,
            messages=messages,
            transparency=transparency,
        ):
            if event["event"] == "token":
                text = str(event["data"].get("text") or "")
                if text:
                    emitted = True
                    parts.append(text)
                    yield _chunk(
                        chat_id=chat_id, created=created, delta={"content": text}
                    )
            elif event["event"] == "done":
                final = event["data"]
    except agent.LLMError as exc:
        error = {"code": exc.code, "message": exc.message}
    except agent.TurnTimeout:
        error = {"code": "timeout", "message": "assistant turn timed out"}
    except (GeneratorExit, asyncio.CancelledError):
        _audit_call(None, key_id=key_id, action="openai.chat", ok=False, error="cancelled")
        raise
    except Exception:
        logger.exception("external openai stream failed")
        error = {"code": "internal_error", "message": "assistant turn failed"}

    if error is not None:
        yield f"data: {json.dumps(_openai_error(error['code'], error['message']), ensure_ascii=False)}\n\n"
        _audit_call(None, key_id=key_id, action="openai.chat", ok=False, error=error["code"])
    else:
        content = (final or {}).get("content") or "".join(parts)
        if not emitted and content:
            yield _chunk(chat_id=chat_id, created=created, delta={"content": content})
        citations = (final or {}).get("citations") or []
        yield _chunk(
            chat_id=chat_id,
            created=created,
            delta={},
            finish_reason="stop",
            usage=_openai_usage((final or {}).get("usage")),
            citations=citations,
        )
        _audit_call(None, key_id=key_id, action="openai.chat", ok=True)
    yield "data: [DONE]\n\n"


__all__ = ["router"]

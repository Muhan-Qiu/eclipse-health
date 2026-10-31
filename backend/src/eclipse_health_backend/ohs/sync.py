"""OHS 日汇总同步。

只读取最近 N 天（默认 30）的 daily 数据，映射成 B4 的
``org.eclipsehealth.health.*`` 记录形态；按 ``externalId`` 去重。
单条写入失败只计数，不回滚已经写入的记录。

OHS 的 daily 字段名并未随本项目固定；这里用一组明确的别名解析，
无法确认单位或结构的字段只记录 warning 并跳过，不做猜测性换算。
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from ..db.models import RecordTable
from ..domain.errors import InvalidInputError
from ..importers.base import HealthRecordDraft
from ..importers.persist import create_health_record
from . import store
from .client import OhsClient, OhsPermissionError

logger = logging.getLogger(__name__)

MODULE_ID = "org.eclipsehealth.ohs"
IMPORT_SOURCE = "open-health-sync"
DEFAULT_DAYS = 30
MAX_DAYS = 90
MAX_WARNINGS = 50
HEALTH_PREFIX = "org.eclipsehealth.health."

KIND_RECORD_TYPES = {
    "steps": "org.eclipsehealth.health.steps",
    "heart-rate": "org.eclipsehealth.health.heart-rate",
    "sleep": "org.eclipsehealth.health.sleep",
    "body-mass": "org.eclipsehealth.health.body-mass",
    "blood-pressure": "org.eclipsehealth.health.blood-pressure",
}

STEPS_KEYS = ("steps", "stepcount", "stepstotal", "totalsteps", "countsteps")
RESTING_HR_KEYS = (
    "restingheartrate",
    "restingheartratebpm",
    "restingheartrateavg",
    "restinghr",
    "rhr",
    "restingpulse",
)
SLEEP_MINUTE_KEYS = (
    "sleepminutes",
    "sleepdurationminutes",
    "sleepdurationmin",
    "totalsleepminutes",
    "asleepminutes",
)
SLEEP_SECOND_KEYS = (
    "sleepseconds",
    "sleepdurationseconds",
    "sleepdurationsec",
    "asleepseconds",
)
SLEEP_HOUR_KEYS = ("sleephours", "sleepdurationhours", "asleephours")
WEIGHT_KG_KEYS = ("weightkg", "bodymasskg", "weightkilograms")
WEIGHT_LB_KEYS = ("weightlbs", "weightpounds", "weightlb")
BP_NESTED_KEYS = ("bloodpressure", "bp")
SYS_KEYS = ("systolic", "sys", "bloodpressuresystolic", "bpsystolic", "systolicpressure")
DIA_KEYS = ("diastolic", "dia", "bloodpressurediastolic", "bpdiaastolic", "diastolicpressure")


@dataclass(slots=True)
class SyncResult:
    created: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    user_id: str | None = None
    days: int = DEFAULT_DAYS

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "warnings": self.warnings,
            "userId": self.user_id,
            "days": self.days,
        }


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _metrics(entry: dict[str, Any]) -> dict[str, Any]:
    """把顶层与常见嵌套层合并成小写无分隔符的字段表。"""
    merged: dict[str, Any] = {}
    for key, value in entry.items():
        merged[_normalize_key(str(key))] = value
    for nested_key in ("metrics", "summary", "values", "stats", "daily", "data"):
        nested = entry.get(nested_key)
        if isinstance(nested, dict):
            for key, value in nested.items():
                merged.setdefault(_normalize_key(str(key)), value)
    return merged


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _parse_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 1_000_000_000_000:  # 毫秒时间戳
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _entry_day(entry: dict[str, Any]) -> date | None:
    metrics = _metrics(entry)
    for key in ("date", "day", "startdate", "startat", "timestamp", "datetime", "time"):
        day = _parse_day(metrics.get(key))
        if day is not None:
            return day
    return None


def _warn(result: SyncResult, code: str, message: str, **details: Any) -> None:
    if len(result.warnings) >= MAX_WARNINGS:
        return
    warning: dict[str, Any] = {"code": code, "message": message}
    warning.update({key: value for key, value in details.items() if value is not None})
    result.warnings.append(warning)


def _payload(value: Any, unit: str, start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "startAt": start.isoformat(),
        "endAt": end.isoformat(),
        "sourceApp": IMPORT_SOURCE,
    }


def _draft(
    *,
    kind: str,
    user_id: str,
    day: date,
    value: Any,
    unit: str,
    payload: dict[str, Any],
    duration_sec: float | None = None,
) -> HealthRecordDraft:
    return HealthRecordDraft(
        record_type=KIND_RECORD_TYPES[kind],
        kind=kind,
        captured_at=datetime.combine(day, time.min, tzinfo=UTC),
        external_id=f"ohs:{user_id}:{day.isoformat()}:{kind}",
        unit=unit,
        duration_sec=duration_sec,
        source_app=IMPORT_SOURCE,
        payload=payload,
        metadata={
            "source": IMPORT_SOURCE,
            "ohsUserId": user_id,
            "ohsDate": day.isoformat(),
            "aggregation": "daily",
        },
    )


def _sleep_minutes(entry: dict[str, Any]) -> tuple[float | None, str | None]:
    """返回 (分钟, 警告码)。只接受带明确单位的字段。"""
    metrics = _metrics(entry)
    minutes = _as_number(_first(metrics, SLEEP_MINUTE_KEYS))
    if minutes is not None:
        return minutes, None
    seconds = _as_number(_first(metrics, SLEEP_SECOND_KEYS))
    if seconds is not None:
        return seconds / 60.0, None
    hours = _as_number(_first(metrics, SLEEP_HOUR_KEYS))
    if hours is not None:
        return hours * 60.0, None
    nested = metrics.get("sleep")
    if isinstance(nested, dict):
        inner = {_normalize_key(str(key)): value for key, value in nested.items()}
        unit = str(inner.get("unit") or "").strip().lower()
        raw = _as_number(inner.get("value") or inner.get("duration") or inner.get("total"))
        if raw is not None:
            if unit in {"min", "mins", "minute", "minutes"}:
                return raw, None
            if unit in {"s", "sec", "secs", "second", "seconds"}:
                return raw / 60.0, None
            if unit in {"h", "hr", "hrs", "hour", "hours"}:
                return raw * 60.0, None
            return None, "ohs_sleep_unit_unknown"
    if nested is not None:
        return None, "ohs_sleep_unit_unknown"
    return None, None


def _blood_pressure(entry: dict[str, Any]) -> tuple[tuple[float, float] | None, str]:
    """返回 ((收缩压, 舒张压), 警告码)。默认 mm[Hg]，kPa 会换算。"""
    metrics = _metrics(entry)
    nested = _first(metrics, BP_NESTED_KEYS)
    unit = ""
    systolic = diastolic = None
    if isinstance(nested, dict):
        inner = {_normalize_key(str(key)): value for key, value in nested.items()}
        systolic = _as_number(_first(inner, SYS_KEYS))
        diastolic = _as_number(_first(inner, DIA_KEYS))
        unit = str(inner.get("unit") or "").strip().lower()
    elif nested is not None:
        return None, "ohs_blood_pressure_invalid"
    if systolic is None:
        systolic = _as_number(_first(metrics, SYS_KEYS))
    if diastolic is None:
        diastolic = _as_number(_first(metrics, DIA_KEYS))
    unit = unit or str(metrics.get("bloodpressureunit") or "").strip().lower()
    if systolic is None and diastolic is None:
        return None, ""
    if systolic is None or diastolic is None:
        return None, "ohs_blood_pressure_incomplete"
    if unit in {"kpa"}:
        systolic *= 7.50062
        diastolic *= 7.50062
    elif unit not in {"", "mmhg", "mm[hg]", "mm hg"}:
        return None, "ohs_bp_unit_unknown"
    if not (30 <= systolic <= 300 and 20 <= diastolic <= 200):
        return None, "ohs_blood_pressure_invalid"
    return (systolic, diastolic), ""


def parse_daily_entry(entry: dict[str, Any], user_id: str) -> list[HealthRecordDraft]:
    """把一条 OHS daily 记录拆成若干健康数据 draft；无法识别的字段跳过。"""
    day = _entry_day(entry)
    if day is None:
        return []
    metrics = _metrics(entry)
    day_start = datetime.combine(day, time.min, tzinfo=UTC)
    drafts: list[HealthRecordDraft] = []

    steps = _as_number(_first(metrics, STEPS_KEYS))
    if steps is not None and steps >= 0:
        value = round(steps)
        drafts.append(
            _draft(
                kind="steps",
                user_id=user_id,
                day=day,
                value=value,
                unit="count",
                payload=_payload(value, "count", day_start, day_start),
            )
        )

    heart = _as_number(_first(metrics, RESTING_HR_KEYS))
    if heart is not None and 0 < heart <= 400:
        value = round(heart, 1)
        drafts.append(
            _draft(
                kind="heart-rate",
                user_id=user_id,
                day=day,
                value=value,
                unit="count/min",
                payload=_payload(value, "count/min", day_start, day_start),
                duration_sec=0.0,
            )
        )

    minutes, _sleep_warning = _sleep_minutes(entry)
    if minutes is not None and 0 < minutes <= 24 * 60:
        end = day_start + timedelta(minutes=minutes)
        drafts.append(
            _draft(
                kind="sleep",
                user_id=user_id,
                day=day,
                value="asleep",
                unit="1",
                payload=_payload("asleep", "1", day_start, end),
                duration_sec=minutes * 60.0,
            )
        )

    weight = _as_number(_first(metrics, WEIGHT_KG_KEYS))
    if weight is None:
        pounds = _as_number(_first(metrics, WEIGHT_LB_KEYS))
        if pounds is not None:
            weight = pounds * 0.45359237
    if weight is None:
        nested_weight = metrics.get("weight")
        if isinstance(nested_weight, dict):
            inner = {_normalize_key(str(key)): value for key, value in nested_weight.items()}
            unit = str(inner.get("unit") or "kg").strip().lower()
            raw = _as_number(_first(inner, ("value", "kg", "kilograms")))
            if raw is not None:
                weight = raw * 0.45359237 if unit in {"lb", "lbs", "pounds"} else raw
    if weight is not None and 2 <= weight <= 500:
        value = round(weight, 2)
        drafts.append(
            _draft(
                kind="body-mass",
                user_id=user_id,
                day=day,
                value=value,
                unit="kg",
                payload=_payload(value, "kg", day_start, day_start),
            )
        )

    pressure, _bp_warning = _blood_pressure(entry)
    if pressure is not None:
        systolic, diastolic = pressure
        value = {
            "systolic": round(systolic, 1),
            "diastolic": round(diastolic, 1),
        }
        drafts.append(
            _draft(
                kind="blood-pressure",
                user_id=user_id,
                day=day,
                value=value,
                unit="mm[Hg]",
                payload=_payload(value, "mm[Hg]", day_start, day_start),
            )
        )

    return drafts


def _existing_external_ids(session: Session) -> set[str]:
    extract = func.json_extract(RecordTable.data, "$.metadata.externalId")
    statement = select(extract).where(
        RecordTable.record_type.startswith(HEALTH_PREFIX),
        RecordTable.deleted_at.is_(None),
        extract.is_not(None),
    )
    return {str(value) for value in session.exec(statement) if value}


def _entry_reports_problem(entry: dict[str, Any]) -> tuple[str, str] | None:
    """返回 (code, message) 描述该条目可确认的字段问题。"""
    day = _entry_day(entry)
    if day is None:
        return ("ohs_entry_without_date", "有一条日汇总缺少可识别的日期，已跳过。")
    _, sleep_warning = _sleep_minutes(entry)
    if sleep_warning:
        return (
            sleep_warning,
            f"{day.isoformat()} 的睡眠字段没有可识别单位，已跳过睡眠。",
        )
    _, bp_warning = _blood_pressure(entry)
    if bp_warning:
        return (
            bp_warning,
            f"{day.isoformat()} 的血压字段不完整或单位未知，已跳过血压。",
        )
    if not parse_daily_entry(entry, "probe"):
        return (
            "ohs_unknown_daily_fields",
            f"{day.isoformat()} 没有可识别的步数/静息心率/睡眠/体重/血压字段。",
        )
    return None


def sync_recent(
    session: Session,
    member_id: str,
    *,
    days: int = DEFAULT_DAYS,
    client: OhsClient | None = None,
    end_date: date | None = None,
) -> SyncResult:
    if days < 1 or days > MAX_DAYS:
        raise InvalidInputError(
            f"同步天数必须在 1–{MAX_DAYS} 之间",
            code="ohs_invalid_days",
            details={"days": days},
        )
    config = store.load_config()
    if not config.token:
        raise InvalidInputError(
            "尚未配置 OHS token",
            code="ohs_not_configured",
        )

    owned = client is None
    active = client or OhsClient(config.base_url, config.token)
    result = SyncResult(days=days)
    try:
        user_id = config.user_id
        if not user_id:
            users = active.list_users()
            if not users:
                raise OhsPermissionError(
                    "无法从 /v1/users 取得用户，请在设置中填写 user id",
                    code="ohs_user_required",
                )
            user_id = users[0]["id"]
        result.user_id = user_id

        last_day = end_date or datetime.now(UTC).date()
        first_day = last_day - timedelta(days=days - 1)
        entries = active.fetch_daily(user_id, first_day, last_day)
        if not entries:
            _warn(result, "ohs_no_daily_data", "OHS 在所选时间范围内没有日汇总数据。")

        existing = _existing_external_ids(session)
        for entry in entries:
            problem = _entry_reports_problem(entry)
            if problem:
                _warn(result, problem[0], problem[1])
            for draft in parse_daily_entry(entry, user_id):
                if draft.external_id in existing:
                    result.skipped += 1
                    continue
                try:
                    create_health_record(
                        session,
                        draft,
                        member_id=member_id,
                        timezone="UTC",
                        module_id=MODULE_ID,
                        import_source=IMPORT_SOURCE,
                        fallback_captured_at=draft.captured_at,
                    )
                    session.commit()
                except Exception:
                    logger.warning("OHS sync: record failed", exc_info=True)
                    session.rollback()
                    result.failed += 1
                    _warn(
                        result,
                        "ohs_record_failed",
                        f"{draft.external_id} 写入失败，已跳过。",
                    )
                    continue
                existing.add(draft.external_id)
                result.created += 1
    finally:
        if owned:
            active.close()

    summary = result.to_dict()
    summary["syncedAt"] = datetime.now(UTC).isoformat()
    summary["rangeStart"] = first_day.isoformat()
    summary["rangeEnd"] = last_day.isoformat()
    store.record_last_sync(summary)
    return result


__all__ = [
    "DEFAULT_DAYS",
    "KIND_RECORD_TYPES",
    "MODULE_ID",
    "SyncResult",
    "parse_daily_entry",
    "sync_recent",
]

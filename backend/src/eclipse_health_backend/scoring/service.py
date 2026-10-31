"""规则评分服务（G2）。

设计约束：
- 只读最近 30 天的记录（睡眠/步数用 7 天窗口），缺项不参与总分；
- 每项规则都是公开健康建议区间，不包含诊断；
- 同一条记录可能同时来自导入与手动指标，取最近一次有效值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from ..db.analysis_repo import measurements_for
from ..db.models import AnalysisTable, RecordTable
from ..db.repositories import get_member_row, list_member_rows, member_from_row
from ..domain.common import utc_now
from ..domain.models import Member
from .models import (
    DISCLAIMER,
    WINDOW_DAYS,
    CategoryId,
    ScoreCategory,
    ScoreReport,
    grade_for,
)

HEART_RATE_RECORD_TYPE = "org.eclipsehealth.health.heart-rate"
SLEEP_RECORD_TYPE = "org.eclipsehealth.health.sleep"
BODY_MASS_RECORD_TYPE = "org.eclipsehealth.health.body-mass"
BLOOD_PRESSURE_RECORD_TYPE = "org.eclipsehealth.health.blood-pressure"
STEPS_RECORD_TYPE = "org.eclipsehealth.health.steps"
METRIC_RECORD_TYPE = "org.eclipsehealth.metric"
ECG_RECORD_TYPE = "org.eclipsehealth.ecg"

ACTIVITY_TARGET_STEPS = 8000
SLEEP_WINDOW_DAYS = 7
ACTIVITY_WINDOW_DAYS = 7

CATEGORY_ORDER: tuple[CategoryId, ...] = (
    "heart",
    "sleep",
    "weight",
    "activity",
    "blood_pressure",
)
CATEGORY_LABELS: dict[CategoryId, str] = {
    "heart": "心脏",
    "sleep": "睡眠",
    "weight": "体重",
    "activity": "活动",
    "blood_pressure": "血压",
}

SLEEP_STAGE_DEEP = "deep"
SLEEP_STAGE_REM = "rem"
SLEEP_STAGE_LIGHT = "light"
SLEEP_STAGE_AWAKE = "awake"
SLEEP_STAGE_IN_BED = "in-bed"


@dataclass(slots=True)
class _Category:
    id: CategoryId
    score: int | None = None
    factors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    evidence_count: int = 0

    def to_model(self) -> ScoreCategory:
        return ScoreCategory(
            id=self.id,
            label=CATEGORY_LABELS[self.id],
            score=self.score,
            grade=grade_for(self.score),
            factors=self.factors,
            missing=self.missing,
            evidenceCount=self.evidence_count,
        )


# --------------------------------------------------------------------- helpers
def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _weights(values: list[tuple[int, float]]) -> int | None:
    total = sum(weight for _score, weight in values)
    if total <= 0:
        return None
    return round(sum(score * weight for score, weight in values) / total)


def _local_date(moment: datetime, timezone: str) -> date:
    try:
        zone = ZoneInfo(timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = UTC
    return moment.astimezone(zone).date()


def _records(
    session: Session,
    member_id: str,
    record_types: tuple[str, ...],
    since: datetime,
    *,
    limit: int = 5000,
) -> list[RecordTable]:
    statement = (
        select(RecordTable)
        .where(
            RecordTable.member_id == member_id,
            RecordTable.record_type.in_(record_types),
            RecordTable.deleted_at.is_(None),
            RecordTable.captured_at >= since,
        )
        .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
        .limit(limit)
    )
    return list(session.exec(statement))


def _member_records(
    session: Session, member_id: str, record_type: str, since: datetime, *, limit: int = 5000
) -> list[RecordTable]:
    return _records(session, member_id, (record_type,), since, limit=limit)


def _metric_records(session: Session, member_id: str, since: datetime) -> list[RecordTable]:
    return _member_records(session, member_id, METRIC_RECORD_TYPE, since, limit=2000)


def _payload_value(row: RecordTable) -> Any:
    return (row.payload or {}).get("value")


def _metric_values(row: RecordTable) -> dict[str, Any]:
    values = (row.payload or {}).get("values")
    return values if isinstance(values, dict) else {}


def _analysis_rows(
    session: Session, member_id: str, since: datetime, *, limit: int = 50
) -> list[AnalysisTable]:
    statement = (
        select(AnalysisTable)
        .join(RecordTable, AnalysisTable.record_id == RecordTable.id)
        .where(
            RecordTable.member_id == member_id,
            RecordTable.deleted_at.is_(None),
            AnalysisTable.status == "completed",
            RecordTable.captured_at >= since,
        )
        .order_by(AnalysisTable.created_at.desc(), AnalysisTable.id.desc())
        .limit(limit)
    )
    return list(session.exec(statement))


def _measurement_map(row: AnalysisTable) -> dict[str, dict[str, Any]]:
    raw = (row.data or {}).get("measurements") or []
    return {
        str(item.get("code")): item
        for item in raw
        if isinstance(item, dict) and item.get("code")
    }


def _analysis_quality(row: AnalysisTable) -> float | None:
    quality = (row.data or {}).get("quality")
    if not isinstance(quality, dict):
        return None
    score = _to_number(quality.get("score"))
    if score is not None:
        return min(max(score, 0.0), 1.0)
    level = quality.get("level")
    return {"good": 0.9, "fair": 0.7, "poor": 0.4}.get(level)  # type: ignore[arg-type]


def _record_quality(row: RecordTable) -> float | None:
    quality = (row.data or {}).get("quality")
    if not isinstance(quality, dict):
        return None
    score = _to_number(quality.get("score"))
    if score is not None:
        return min(max(score, 0.0), 1.0)
    level = quality.get("level")
    return {"good": 0.9, "fair": 0.7, "poor": 0.4}.get(level)  # type: ignore[arg-type]


def _resolve_member(session: Session, member_id: str | None) -> Member | None:
    if member_id:
        row = get_member_row(session, member_id)
        return member_from_row(row) if row is not None else None
    rows = list_member_rows(session)
    return member_from_row(rows[0]) if rows else None


def _is_resting(row: RecordTable) -> bool:
    payload = row.payload or {}
    metadata = row.data.get("metadata") or {}
    if payload.get("resting") is True or metadata.get("resting") is True:
        return True
    return "resting" in {str(tag).lower() for tag in row.data.get("tags") or []}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = round((len(ordered) - 1) * fraction)
    return ordered[min(max(index, 0), len(ordered) - 1)]


# ---------------------------------------------------------------------- heart
def _score_resting_hr(value: float) -> int:
    if 50 <= value <= 70:
        return 100
    if 45 <= value < 50 or 70 < value <= 80:
        return 85
    if 40 <= value < 45 or 80 < value <= 90:
        return 70
    if 35 <= value < 40 or 90 < value <= 100:
        return 55
    return 40


def _score_hrv(value: float) -> int:
    if value >= 50:
        return 100
    if value >= 40:
        return 85
    if value >= 30:
        return 70
    if value >= 20:
        return 55
    return 40


def _score_abnormal(value: float) -> int:
    if value <= 1:
        return 100
    if value <= 3:
        return 90
    if value <= 5:
        return 75
    if value <= 10:
        return 60
    if value <= 15:
        return 45
    return 30


def _heart_rate_from_health(
    session: Session, member_id: str, since: datetime
) -> tuple[float | None, bool]:
    rows = _member_records(session, member_id, HEART_RATE_RECORD_TYPE, since)
    values = [
        value
        for row in rows
        if (value := _to_number(_payload_value(row))) is not None and 20 <= value <= 250
    ]
    if not values:
        return None, False
    resting = [
        value
        for row in rows
        if _is_resting(row)
        and (value := _to_number(_payload_value(row))) is not None
        and 20 <= value <= 250
    ]
    if resting:
        return sum(resting) / len(resting), True
    return _percentile(values, 0.10), False


def _heart_analysis_metrics(
    session: Session, member_id: str, since: datetime
) -> tuple[float | None, float | None, float | None, float | None]:
    """返回最新可用分析的 (平均心率, RMSSD, 异常搏动%, 质量 0-1)。"""
    heart_rate = rmssd = abnormal = quality = None
    for row in _analysis_rows(session, member_id, since):
        measurements = _measurement_map(row) or {
            str(item.get("code")): item for item in measurements_for(session, row.id)
        }
        if heart_rate is None:
            heart_rate = _to_number((measurements.get("heart_rate_mean") or {}).get("value"))
        if rmssd is None:
            rmssd = _to_number((measurements.get("rmssd") or {}).get("value"))
        if abnormal is None:
            ratios = [
                _to_number((measurements.get(code) or {}).get("value"))
                for code in ("svb_ratio", "veb_ratio", "f_ratio")
            ]
            present = [value for value in ratios if value is not None]
            abnormal = sum(present) if present else None
        if quality is None:
            quality = _analysis_quality(row)
        if heart_rate is not None and rmssd is not None and abnormal is not None and quality:
            break
    if quality is None:
        ecg_rows = _member_records(session, member_id, ECG_RECORD_TYPE, since, limit=50)
        quality = next(
            (value for row in ecg_rows if (value := _record_quality(row)) is not None), None
        )
    return heart_rate, rmssd, abnormal, quality


def _build_heart(session: Session, member: Member, now: datetime) -> _Category:
    since = now - timedelta(days=WINDOW_DAYS)
    category = _Category(id="heart")
    parts: list[tuple[int, float]] = []

    resting_hr, is_resting = _heart_rate_from_health(session, member.id, since)
    ecg_hr, rmssd, abnormal, quality = _heart_analysis_metrics(session, member.id, since)
    heart_rate = resting_hr if resting_hr is not None else ecg_hr

    if heart_rate is not None:
        if resting_hr is not None:
            detail = "静息心率" if is_resting else "静息心率约"
            category.factors.append(f"{detail} {heart_rate:.0f} bpm（近 30 天）")
        else:
            category.factors.append(f"最近心电图平均心率 {heart_rate:.0f} bpm")
        parts.append((_score_resting_hr(heart_rate), 0.40))
    else:
        category.missing.append("缺少静息心率或心电图平均心率")

    if rmssd is not None:
        category.factors.append(f"HRV（RMSSD）{rmssd:.0f} ms")
        parts.append((_score_hrv(rmssd), 0.25))
    else:
        category.missing.append("缺少可用的 HRV（RMSSD）分析结果")

    if abnormal is not None:
        category.factors.append(f"异常搏动占比 {abnormal:.1f}%")
        parts.append((_score_abnormal(abnormal), 0.20))
    else:
        category.missing.append("缺少心电图搏动分类结果")

    if quality is not None:
        category.factors.append(f"最近心电图信号质量 {quality:.2f}")
        parts.append((round(quality * 100), 0.15))
    else:
        category.missing.append("缺少信号质量数据")

    category.score = _weights(parts)
    category.evidence_count = len(parts)
    if category.score is None:
        category.missing = ["缺少心率与心电图数据"]
    return category


# ---------------------------------------------------------------------- sleep
def _sleep_stage(row: RecordTable) -> str:
    value = _payload_value(row)
    text = str(value or "").strip().lower()
    if "deep" in text:
        return SLEEP_STAGE_DEEP
    if "rem" in text:
        return SLEEP_STAGE_REM
    if "awake" in text:
        return SLEEP_STAGE_AWAKE
    if "in-bed" in text or "inbed" in text or "in bed" in text:
        return SLEEP_STAGE_IN_BED
    if any(token in text for token in ("asleep", "sleep", "light", "core")):
        return SLEEP_STAGE_LIGHT
    return SLEEP_STAGE_LIGHT


def _sleep_seconds(row: RecordTable) -> float:
    duration = _to_number(row.data.get("durationSec"))
    if duration is not None:
        return max(0.0, duration)
    value = _to_number(_payload_value(row))
    # 小米睡眠数值通常以分钟计。
    return max(0.0, value * 60.0) if value is not None else 0.0


def _score_sleep_hours(hours: float) -> int:
    if 7 <= hours <= 9:
        return 100
    if 6 <= hours < 7 or 9 < hours <= 10:
        return 85
    if 5 <= hours < 6 or 10 < hours <= 11:
        return 65
    return 45


def _score_sleep_ratio(ratio: float) -> int:
    if 33 <= ratio <= 48:
        return 100
    if 28 <= ratio < 33 or 48 < ratio <= 53:
        return 85
    if 23 <= ratio < 28 or 53 < ratio <= 58:
        return 70
    if 18 <= ratio < 23 or 58 < ratio <= 65:
        return 55
    return 40


def _build_sleep(session: Session, member: Member, now: datetime) -> _Category:
    category = _Category(id="sleep")
    rows = _member_records(
        session, member.id, SLEEP_RECORD_TYPE, now - timedelta(days=SLEEP_WINDOW_DAYS)
    )
    nightly: dict[date, float] = {}
    stages: dict[str, float] = {}
    for row in rows:
        stage = _sleep_stage(row)
        if stage in {SLEEP_STAGE_AWAKE, SLEEP_STAGE_IN_BED}:
            continue
        seconds = _sleep_seconds(row)
        if seconds <= 0:
            continue
        day = _local_date(row.captured_at, row.data.get("timezone") or "UTC")
        nightly[day] = nightly.get(day, 0.0) + seconds
        stages[stage] = stages.get(stage, 0.0) + seconds

    nights = len(nightly)
    if nights == 0:
        category.missing = ["缺少睡眠记录"]
        return category

    average_hours = sum(nightly.values()) / nights / 3600.0
    category.evidence_count = nights
    category.factors.append(f"近 7 天平均睡眠 {average_hours:.1f} h（{nights} 晚）")
    parts: list[tuple[int, float]] = [(_score_sleep_hours(average_hours), 0.70)]

    deep = stages.get(SLEEP_STAGE_DEEP, 0.0)
    rem = stages.get(SLEEP_STAGE_REM, 0.0)
    light = stages.get(SLEEP_STAGE_LIGHT, 0.0)
    total = deep + rem + light
    if deep + rem > 0 and light > 0 and total > 0:
        ratio = (deep + rem) / total * 100.0
        category.factors.append(f"深睡/REM 占比 {ratio:.0f}%")
        parts.append((_score_sleep_ratio(ratio), 0.30))
    else:
        category.missing.append("缺少深睡/REM 分期数据")

    category.score = _weights(parts)
    return category


# --------------------------------------------------------------------- weight
def _score_bmi(bmi: float) -> int:
    if 18.5 <= bmi < 24:
        return 100
    if 24 <= bmi < 28 or 17 <= bmi < 18.5:
        return 75
    if 28 <= bmi < 30:
        return 60
    if 30 <= bmi < 35 or 15 <= bmi < 17:
        return 45
    return 30


def _latest_body_mass(
    session: Session, member_id: str, since: datetime
) -> tuple[float, datetime] | None:
    rows = _member_records(session, member_id, BODY_MASS_RECORD_TYPE, since, limit=10)
    for row in rows:
        value = _to_number(_payload_value(row))
        if value is not None and 2 <= value <= 500:
            return value, row.captured_at
    return None


def _latest_metric_weight(
    session: Session, member_id: str, since: datetime
) -> tuple[float, datetime] | None:
    for row in _metric_records(session, member_id, since):
        if (row.payload or {}).get("kind") != "weight":
            continue
        value = _to_number(_metric_values(row).get("weight"))
        if value is not None and 2 <= value <= 500:
            return value, row.captured_at
    return None


def _build_weight(session: Session, member: Member, now: datetime) -> _Category:
    category = _Category(id="weight")
    since = now - timedelta(days=WINDOW_DAYS)
    candidates = [
        item
        for item in (
            _latest_body_mass(session, member.id, since),
            _latest_metric_weight(session, member.id, since),
        )
        if item is not None
    ]
    weight = max(candidates, key=lambda item: item[1])[0] if candidates else member.weightKg
    height = member.heightCm

    if height is None:
        category.missing.append("缺少身高")
    if weight is None:
        category.missing.append("缺少体重")
    if height is None or weight is None:
        return category

    bmi = weight / ((height / 100.0) ** 2)
    category.score = _score_bmi(bmi)
    category.evidence_count = 1
    category.factors.append(f"BMI {bmi:.1f}（身高 {height:.0f} cm，体重 {weight:.1f} kg）")
    return category


# ------------------------------------------------------------------- activity
def _score_steps(steps: float) -> int:
    return max(0, min(100, round(steps / ACTIVITY_TARGET_STEPS * 100)))


def _build_activity(session: Session, member: Member, now: datetime) -> _Category:
    category = _Category(id="activity")
    rows = _member_records(
        session, member.id, STEPS_RECORD_TYPE, now - timedelta(days=ACTIVITY_WINDOW_DAYS)
    )
    daily: dict[date, float] = {}
    for row in rows:
        value = _to_number(_payload_value(row))
        if value is None or value < 0:
            continue
        day = _local_date(row.captured_at, row.data.get("timezone") or "UTC")
        daily[day] = daily.get(day, 0.0) + value

    if not daily:
        category.missing = ["缺少步数记录"]
        return category

    average = sum(daily.values()) / len(daily)
    category.score = _score_steps(average)
    category.evidence_count = len(daily)
    category.factors.append(
        f"近 7 天日均 {average:.0f} 步（目标 {ACTIVITY_TARGET_STEPS} 步）"
    )
    return category


# -------------------------------------------------------------- blood pressure
def _score_blood_pressure(systolic: float, diastolic: float) -> int:
    if systolic < 90 or diastolic < 60:
        return 65
    if systolic < 120 and diastolic < 80:
        return 100
    if systolic < 130 and diastolic < 80:
        return 85
    if systolic < 140 or diastolic < 90:
        return 65
    if systolic < 160 or diastolic < 100:
        return 45
    return 30


def _latest_blood_pressure(
    session: Session, member_id: str, since: datetime
) -> tuple[float, float, datetime] | None:
    found: tuple[float, float, datetime] | None = None
    for row in _member_records(
        session, member_id, BLOOD_PRESSURE_RECORD_TYPE, since, limit=50
    ):
        value = _payload_value(row)
        if not isinstance(value, dict):
            continue
        systolic = _to_number(value.get("systolic"))
        diastolic = _to_number(value.get("diastolic"))
        if systolic is None or diastolic is None:
            continue
        if found is None or row.captured_at > found[2]:
            found = (systolic, diastolic, row.captured_at)
    for row in _metric_records(session, member_id, since):
        if (row.payload or {}).get("kind") != "blood_pressure":
            continue
        values = _metric_values(row)
        systolic = _to_number(values.get("systolic"))
        diastolic = _to_number(values.get("diastolic"))
        if systolic is None or diastolic is None:
            continue
        if found is None or row.captured_at > found[2]:
            found = (systolic, diastolic, row.captured_at)
    return found


def _build_blood_pressure(session: Session, member: Member, now: datetime) -> _Category:
    category = _Category(id="blood_pressure")
    found = _latest_blood_pressure(session, member.id, now - timedelta(days=WINDOW_DAYS))
    if found is None:
        category.missing = ["缺少血压记录"]
        return category
    systolic, diastolic, _captured_at = found
    category.score = _score_blood_pressure(systolic, diastolic)
    category.evidence_count = 1
    category.factors.append(f"最近血压 {systolic:.0f}/{diastolic:.0f} mmHg")
    return category


# ---------------------------------------------------------------------- report
def empty_report(now: datetime | None = None, member_id: str | None = None) -> ScoreReport:
    return ScoreReport(
        overall=None,
        grade="unknown",
        categories=[],
        missing=[CATEGORY_LABELS[item] for item in CATEGORY_ORDER],
        disclaimer=DISCLAIMER,
        generatedAt=now or utc_now(),
        memberId=member_id,
        windowDays=WINDOW_DAYS,
    )


def build_score_report(
    session: Session,
    *,
    member_id: str | None = None,
    now: datetime | None = None,
) -> ScoreReport:
    moment = now or utc_now()
    member = _resolve_member(session, member_id)
    if member is None:
        return empty_report(moment, member_id)

    built = [
        _build_heart(session, member, moment),
        _build_sleep(session, member, moment),
        _build_weight(session, member, moment),
        _build_activity(session, member, moment),
        _build_blood_pressure(session, member, moment),
    ]
    available = [item for item in built if item.score is not None]
    overall: int | None = None
    if available:
        total_score = sum(item.score for item in available if item.score is not None)
        overall = round(total_score / len(available))
    return ScoreReport(
        overall=overall,
        grade=grade_for(overall),
        categories=[item.to_model() for item in available],
        missing=[CATEGORY_LABELS[item.id] for item in built if item.score is None],
        disclaimer=DISCLAIMER,
        generatedAt=moment,
        memberId=member.id,
        windowDays=WINDOW_DAYS,
    )


__all__ = [
    "ACTIVITY_TARGET_STEPS",
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "SLEEP_WINDOW_DAYS",
    "build_score_report",
    "empty_report",
]

"""卡片类型目录：kind → 记录类型 / 取值规则 / 默认单位。

只读既有 ``records`` 表，不直接读文件，也不执行任何 SQL / 表达式。
新增一种数据类型时只需在这里登记，API、聚合与助手工具会一起生效。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db.models import RecordTable
from ..domain.common import utc_now
from .models import CardAggregation, CardTemplate, CardView

HEALTH_PREFIX = "org.eclipsehealth.health."
METRIC_RECORD_TYPE = "org.eclipsehealth.metric"

# 单张卡片最多扫描的记录数；本地健康数据通常远小于这个数。
MAX_SCAN_RECORDS = 20_000
# 序列最多返回的点数（超出时保留最近的）。
MAX_SERIES_POINTS = 400

AGGREGATIONS: tuple[CardAggregation, ...] = (
    "latest",
    "avg",
    "min",
    "max",
    "sum",
    "count",
)

VIEWS: tuple[CardView, ...] = ("stat", "sparkline", "line", "bar")


@dataclass(frozen=True, slots=True)
class KindSpec:
    key: str
    record_types: tuple[str, ...]
    metric_kind: str | None
    unit: str | None
    label_zh: str
    label_en: str
    # 取值方式：数值字段 / 时长 / 血压对。
    mode: str = "value"
    value_fields: tuple[str, ...] = ()
    metric_field: str | None = None


KINDS: dict[str, KindSpec] = {
    "steps": KindSpec(
        key="steps",
        record_types=(f"{HEALTH_PREFIX}steps",),
        metric_kind=None,
        unit="count",
        label_zh="步数",
        label_en="Steps",
        value_fields=("value", "steps", "count"),
    ),
    "heart-rate": KindSpec(
        key="heart-rate",
        record_types=(f"{HEALTH_PREFIX}heart-rate",),
        metric_kind=None,
        unit="count/min",
        label_zh="心率",
        label_en="Heart rate",
        value_fields=("value", "heartRate", "heart_rate", "bpm"),
    ),
    "sleep": KindSpec(
        key="sleep",
        record_types=(f"{HEALTH_PREFIX}sleep",),
        metric_kind=None,
        unit="min",
        label_zh="睡眠",
        label_en="Sleep",
        mode="duration",
    ),
    "body-mass": KindSpec(
        key="body-mass",
        record_types=(f"{HEALTH_PREFIX}body-mass", METRIC_RECORD_TYPE),
        metric_kind="weight",
        unit="kg",
        label_zh="体重",
        label_en="Body mass",
        value_fields=("value", "weight", "bodyMass"),
        metric_field="weight",
    ),
    "blood-pressure": KindSpec(
        key="blood-pressure",
        record_types=(f"{HEALTH_PREFIX}blood-pressure", METRIC_RECORD_TYPE),
        metric_kind="blood_pressure",
        unit="mmHg",
        label_zh="血压",
        label_en="Blood pressure",
        mode="pair",
    ),
    "exercise": KindSpec(
        key="exercise",
        record_types=(f"{HEALTH_PREFIX}exercise",),
        metric_kind=None,
        unit="min",
        label_zh="运动",
        label_en="Exercise",
        mode="duration",
    ),
    "spo2": KindSpec(
        key="spo2",
        record_types=(f"{HEALTH_PREFIX}spo2", METRIC_RECORD_TYPE),
        metric_kind="spo2",
        unit="%",
        label_zh="血氧",
        label_en="Blood oxygen",
        value_fields=("value", "spo2", "oxygenSaturation"),
        metric_field="spo2",
    ),
    "stress": KindSpec(
        key="stress",
        record_types=(f"{HEALTH_PREFIX}stress",),
        metric_kind=None,
        # 压力各厂商标度不一（0–100 / 1–5），不猜单位；缺失时前端明确提示。
        unit=None,
        label_zh="压力",
        label_en="Stress",
        value_fields=("value", "stress"),
    ),
    "glucose": KindSpec(
        key="glucose",
        record_types=(f"{HEALTH_PREFIX}glucose", METRIC_RECORD_TYPE),
        metric_kind="glucose",
        unit="mmol/L",
        label_zh="血糖",
        label_en="Glucose",
        value_fields=("value", "glucose"),
        metric_field="glucose",
    ),
}

DEFAULT_TEMPLATES: tuple[CardTemplate, ...] = (
    CardTemplate(
        id="stress-latest",
        title="压力 · 最新",
        kind="stress",
        aggregation="latest",
        windowDays=14,
        view="stat",
        colorToken="chart-4",
    ),
    CardTemplate(
        id="stress-trend",
        title="压力 · 趋势",
        kind="stress",
        aggregation="avg",
        windowDays=30,
        view="line",
        colorToken="chart-4",
    ),
    CardTemplate(
        id="spo2-latest",
        title="血氧 · 最新",
        kind="spo2",
        aggregation="latest",
        windowDays=14,
        view="stat",
        unit="%",
        colorToken="chart-2",
    ),
    CardTemplate(
        id="spo2-trend",
        title="血氧 · 趋势",
        kind="spo2",
        aggregation="avg",
        windowDays=30,
        view="line",
        unit="%",
        colorToken="chart-2",
    ),
    CardTemplate(
        id="blood-pressure-latest",
        title="血压 · 最新",
        kind="blood-pressure",
        aggregation="latest",
        windowDays=14,
        view="stat",
        unit="mmHg",
        colorToken="chart-3",
    ),
    CardTemplate(
        id="blood-pressure-trend",
        title="血压 · 趋势",
        kind="blood-pressure",
        aggregation="avg",
        windowDays=30,
        view="line",
        unit="mmHg",
        colorToken="chart-3",
    ),
    CardTemplate(
        id="exercise-weekly",
        title="运动 · 周汇总",
        kind="exercise",
        aggregation="sum",
        windowDays=7,
        view="bar",
        unit="min",
        colorToken="chart-5",
    ),
    CardTemplate(
        id="sleep-duration",
        title="睡眠 · 时长趋势",
        kind="sleep",
        aggregation="avg",
        windowDays=14,
        view="line",
        unit="min",
        colorToken="chart-1",
    ),
)


def spec_for(kind: str) -> KindSpec | None:
    return KINDS.get(kind)


def templates() -> list[CardTemplate]:
    return [template.model_copy() for template in DEFAULT_TEMPLATES]


# --------------------------------------------------------------------------- #
# 取值
# --------------------------------------------------------------------------- #


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _duration_minutes(row: RecordTable, payload: dict[str, Any]) -> float | None:
    seconds = _number(payload.get("durationSec"))
    if seconds is None and row.duration_sec is not None:
        seconds = float(row.duration_sec)
    if seconds is None:
        start = _parse_iso(payload.get("startAt"))
        end = _parse_iso(payload.get("endAt"))
        if start is not None and end is not None and end >= start:
            seconds = (end - start).total_seconds()
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds / 60.0


def extract_values(
    row: RecordTable, spec: KindSpec
) -> tuple[float, float | None] | None:
    """从一条记录里取 (主值, 次值)；取不到返回 ``None``，不填 0。"""
    payload = row.payload or {}

    if row.record_type == METRIC_RECORD_TYPE:
        if payload.get("kind") != spec.metric_kind:
            return None
        values = payload.get("values")
        if not isinstance(values, dict):
            return None
        if spec.mode == "pair":
            systolic = _number(values.get("systolic"))
            diastolic = _number(values.get("diastolic"))
            if systolic is None:
                return None
            return systolic, diastolic
        field = spec.metric_field or ""
        value = _number(values.get(field))
        return (value, None) if value is not None else None

    if spec.mode == "pair":
        raw = payload.get("value")
        if isinstance(raw, dict):
            systolic = _number(raw.get("systolic"))
            diastolic = _number(raw.get("diastolic"))
        else:
            systolic = _number(payload.get("systolic"))
            diastolic = _number(payload.get("diastolic"))
        if systolic is None:
            return None
        return systolic, diastolic

    if spec.mode == "duration":
        minutes = _duration_minutes(row, payload)
        if minutes is None:
            return None
        return minutes, None

    for field in spec.value_fields:
        value = _number(payload.get(field))
        if value is not None:
            return value, None
    return None


# --------------------------------------------------------------------------- #
# 查询与聚合
# --------------------------------------------------------------------------- #


def query_points(
    session: Any,
    *,
    member_id: str,
    kind: str,
    window_days: int,
) -> list[tuple[datetime, float, float | None]]:
    """按成员 + 类型 + 时间窗取出原始点，按时间升序。"""
    from sqlmodel import select

    spec = spec_for(kind)
    if spec is None:
        return []
    since = utc_now() - timedelta(days=max(1, min(365, int(window_days))))
    statement = (
        select(RecordTable)
        .where(
            RecordTable.member_id == member_id,
            RecordTable.record_type.in_(spec.record_types),
            RecordTable.deleted_at.is_(None),
            RecordTable.captured_at >= since,
        )
        .order_by(RecordTable.captured_at.asc(), RecordTable.id.asc())
        .limit(MAX_SCAN_RECORDS)
    )
    points: list[tuple[datetime, float, float | None]] = []
    for row in session.exec(statement):
        extracted = extract_values(row, spec)
        if extracted is None:
            continue
        primary, secondary = extracted
        captured = row.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=UTC)
        points.append((captured.astimezone(UTC), primary, secondary))
    return points


def _round(value: float) -> float:
    return round(value, 6)


def aggregate(values: list[float], aggregation: CardAggregation) -> float | None:
    if not values:
        return None
    if aggregation == "latest":
        return _round(values[-1])
    if aggregation == "avg":
        return _round(sum(values) / len(values))
    if aggregation == "min":
        return _round(min(values))
    if aggregation == "max":
        return _round(max(values))
    if aggregation == "sum":
        return _round(sum(values))
    return float(len(values))


def build_series(
    points: list[tuple[datetime, float, float | None]],
    aggregation: CardAggregation,
) -> list[dict[str, Any]]:
    """按天聚合；``latest`` 直接使用原始点，避免把同一天的多次读数压成一个。"""
    if aggregation == "latest":
        return [
            {"t": moment.isoformat(), "value": _round(value)}
            for moment, value, _secondary in points
        ][-MAX_SERIES_POINTS:]

    buckets: dict[str, list[float]] = {}
    order: list[str] = []
    for moment, value, _secondary in points:
        key = moment.date().isoformat()
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(value)

    series = []
    for key in order:
        value = aggregate(buckets[key], aggregation)
        if value is None:
            continue
        series.append({"t": f"{key}T00:00:00+00:00", "value": value})
    return series[-MAX_SERIES_POINTS:]


__all__ = [
    "AGGREGATIONS",
    "DEFAULT_TEMPLATES",
    "KINDS",
    "MAX_SCAN_RECORDS",
    "MAX_SERIES_POINTS",
    "METRIC_RECORD_TYPE",
    "VIEWS",
    "KindSpec",
    "aggregate",
    "build_series",
    "extract_values",
    "query_points",
    "spec_for",
    "templates",
]

"""教练上下文：评分、健康数据摘要、运动记录、记忆、天气。

所有数据源都是可选的：G2/G3 模块未安装、数据为空、字段损坏时只跳过
对应段落，不抛异常。这里不写日志，也不把记忆内容放进日志或异常信息。
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from ..db.models import RecordTable
from ..db.repositories import get_member_row, member_from_row
from ..domain.common import to_storage_dt, utc_now

HEALTH_PREFIX = "org.eclipsehealth.health."
STEPS_TYPE = f"{HEALTH_PREFIX}steps"
HEART_RATE_TYPE = f"{HEALTH_PREFIX}heart-rate"
SLEEP_TYPE = f"{HEALTH_PREFIX}sleep"
BODY_MASS_TYPE = f"{HEALTH_PREFIX}body-mass"
BLOOD_PRESSURE_TYPE = f"{HEALTH_PREFIX}blood-pressure"
METRIC_TYPE = "org.eclipsehealth.metric"
EXERCISE_TYPE = f"{HEALTH_PREFIX}exercise"

WINDOW_DAYS = 7
HEALTH_TYPES = (STEPS_TYPE, HEART_RATE_TYPE, SLEEP_TYPE, BODY_MASS_TYPE, BLOOD_PRESSURE_TYPE)

GRADE_LABELS = {
    "excellent": "优秀",
    "good": "良好",
    "fair": "一般",
    "attention": "需关注",
    "unknown": "未知",
}

ACTIVITY_LABELS = {
    "walk": "步行",
    "run": "跑步",
    "cycle": "骑行",
    "swim": "游泳",
    "strength": "力量训练",
    "yoga": "瑜伽",
    "other": "其他",
}
INTENSITY_LABELS = {"low": "低强度", "moderate": "中等强度", "vigorous": "高强度"}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _date_key(row: RecordTable, payload: dict[str, Any]) -> str:
    moment = _parse_iso(payload.get("startAt")) or row.captured_at
    return moment.date().isoformat()


def _member(session: Session, member_id: str) -> Any:
    try:
        row = get_member_row(session, member_id)
        return member_from_row(row) if row is not None else None
    except Exception:  # noqa: BLE001 - 档案损坏不影响教练上下文
        return None


def _recent_rows(
    session: Session,
    member_id: str,
    record_types: Iterable[str],
    *,
    days: int = WINDOW_DAYS,
    limit: int = 5000,
) -> list[RecordTable]:
    since = to_storage_dt(utc_now() - timedelta(days=days))
    statement = (
        select(RecordTable)
        .where(
            RecordTable.member_id == member_id,
            RecordTable.record_type.in_(tuple(record_types)),
            RecordTable.deleted_at.is_(None),
            RecordTable.captured_at >= since,
        )
        .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
        .limit(limit)
    )
    return list(session.exec(statement))


# --------------------------------------------------------------------------- #
# G2 评分（惰性导入）
# --------------------------------------------------------------------------- #


def _score_report(session: Session, member_id: str) -> dict[str, Any] | None:
    try:
        from ..scoring.service import build_score_report
    except Exception:  # noqa: BLE001 - G2 未完成时跳过
        return None
    try:
        report = build_score_report(session, member_id=member_id)
    except TypeError:
        try:
            report = build_score_report(session, member_id)
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None
    dump = getattr(report, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except Exception:  # noqa: BLE001
            return None
    return report if isinstance(report, dict) else None


# --------------------------------------------------------------------------- #
# G3 记忆（惰性导入）
# --------------------------------------------------------------------------- #


def _normalize_memory(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    enabled = getattr(value, "enabled", None)
    if isinstance(value, dict):
        enabled = value.get("enabled", enabled)
        content = value.get("content")
    else:
        content = getattr(value, "content", value if isinstance(value, str) else None)
    if enabled is False or not isinstance(content, str) or not content.strip():
        return None
    return {"content": content.strip()}


def _memory_context() -> dict[str, str] | None:
    for module_name in (
        "eclipse_health_backend.memory",
        "eclipse_health_backend.memory.service",
        "eclipse_health_backend.memory.context",
        "eclipse_health_backend.memory.store",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001, S112 - G3 未完成/导入失败时跳过后备位置
            continue
        func = getattr(module, "memory_context", None)
        if not callable(func):
            continue
        try:
            return _normalize_memory(func())
        except Exception:  # noqa: BLE001 - 记忆文件损坏时跳过
            return None
    return None


# --------------------------------------------------------------------------- #
# 健康数据摘要
# --------------------------------------------------------------------------- #


def _steps_summary(rows: list[RecordTable]) -> dict[str, Any] | None:
    daily: dict[str, float] = {}
    for row in rows:
        if row.record_type != STEPS_TYPE:
            continue
        payload = row.payload or {}
        value = _number(payload.get("value"))
        if value is None or value < 0:
            continue
        key = _date_key(row, payload)
        daily[key] = daily.get(key, 0.0) + value
    if not daily:
        return None
    latest = max(daily)
    return {
        "dailyAverage": round(sum(daily.values()) / len(daily)),
        "days": len(daily),
        "latest": round(daily[latest]),
        "latestDate": latest,
    }


def _heart_rate_summary(rows: list[RecordTable], member: Any) -> dict[str, Any] | None:
    values: list[float] = []
    for row in rows:
        if row.record_type != HEART_RATE_TYPE:
            continue
        value = _number((row.payload or {}).get("value"))
        if value is not None and 20 <= value <= 250:
            values.append(value)
    resting = getattr(member, "restingHeartRate", None) if member is not None else None
    resting_value = _number(resting)
    if not values and resting_value is None:
        return None
    summary: dict[str, Any] = {"samples": len(values)}
    if values:
        summary.update(
            {
                "average": _round(sum(values) / len(values)),
                "min": _round(min(values)),
                "max": _round(max(values)),
            }
        )
    if resting_value is not None:
        summary["restingBpm"] = round(resting_value)
    return summary


def _sleep_seconds(row: RecordTable) -> float | None:
    payload = row.payload or {}
    start = _parse_iso(payload.get("startAt"))
    end = _parse_iso(payload.get("endAt"))
    if start is not None and end is not None:
        seconds = (end - start).total_seconds()
        if seconds > 0:
            return seconds
    duration = _number((row.data or {}).get("durationSec"))
    if duration is not None and duration > 0:
        return duration
    value = _number(payload.get("value"))
    unit = str(payload.get("unit") or "").strip().lower()
    if value is not None and value > 0 and unit in {"min", "mins", "minute", "minutes"}:
        return value * 60.0
    return None


def _sleep_category(row: RecordTable) -> str | None:
    payload = row.payload or {}
    metadata = (row.data or {}).get("metadata")
    category = metadata.get("sleepCategory") if isinstance(metadata, dict) else None
    if not category and isinstance(payload.get("value"), str):
        category = payload.get("value")
    return str(category).strip().lower() if category else None


def _sleep_summary(rows: list[RecordTable]) -> dict[str, Any] | None:
    per_day: dict[str, list[tuple[str | None, float]]] = {}
    for row in rows:
        if row.record_type != SLEEP_TYPE:
            continue
        category = _sleep_category(row)
        if category in {"awake", "in-bed"}:
            continue
        seconds = _sleep_seconds(row)
        if seconds is None:
            continue
        per_day.setdefault(_date_key(row, row.payload or {}), []).append((category, seconds))

    daily_hours: dict[str, float] = {}
    for day, items in per_day.items():
        # Apple 同时导出总睡眠与阶段；有总睡眠时只用总睡眠，避免重复计算。
        exact = [seconds for category, seconds in items if category == "asleep"]
        if exact:
            total = sum(exact)
        else:
            total = sum(
                seconds
                for category, seconds in items
                if category is None or category.startswith("asleep")
            )
        if total > 0:
            daily_hours[day] = total / 3600.0
    if not daily_hours:
        return None
    latest = max(daily_hours)
    return {
        "averageHours": _round(sum(daily_hours.values()) / len(daily_hours)),
        "days": len(daily_hours),
        "latestHours": _round(daily_hours[latest]),
        "latestDate": latest,
    }


def _weight_summary(rows: list[RecordTable], member: Any) -> dict[str, Any] | None:
    for row in rows:
        payload = row.payload or {}
        if row.record_type == BODY_MASS_TYPE:
            value = _number(payload.get("value"))
        elif row.record_type == METRIC_TYPE and payload.get("kind") == "weight":
            values = payload.get("values")
            value = _number(values.get("weight")) if isinstance(values, dict) else None
        else:
            continue
        if value is not None and 2 <= value <= 500:
            return {"value": _round(value), "unit": "kg", "measuredAt": row.captured_at.isoformat()}
    profile_weight = getattr(member, "weightKg", None) if member is not None else None
    value = _number(profile_weight)
    if value is not None and 2 <= value <= 500:
        return {"value": _round(value), "unit": "kg", "source": "profile"}
    return None


def _blood_pressure_summary(rows: list[RecordTable]) -> dict[str, Any] | None:
    for row in rows:
        payload = row.payload or {}
        if row.record_type == BLOOD_PRESSURE_TYPE:
            value = payload.get("value")
            if isinstance(value, dict):
                systolic = _number(value.get("systolic"))
                diastolic = _number(value.get("diastolic"))
            else:
                systolic = diastolic = None
        elif row.record_type == METRIC_TYPE and payload.get("kind") == "blood_pressure":
            values = payload.get("values")
            systolic = _number(values.get("systolic")) if isinstance(values, dict) else None
            diastolic = _number(values.get("diastolic")) if isinstance(values, dict) else None
        else:
            continue
        if systolic is None or diastolic is None:
            continue
        if not (50 <= systolic <= 300 and 20 <= diastolic <= 200):
            continue
        return {
            "systolic": round(systolic),
            "diastolic": round(diastolic),
            "unit": "mmHg",
            "measuredAt": row.captured_at.isoformat(),
        }
    return None


def _health_summary(
    session: Session, member_id: str, member: Any
) -> dict[str, Any]:
    rows = _recent_rows(session, member_id, (*HEALTH_TYPES, METRIC_TYPE), limit=4000)
    summary = {
        "steps": _steps_summary(rows),
        "heartRate": _heart_rate_summary(rows, member),
        "sleep": _sleep_summary(rows),
        "weight": _weight_summary(rows, member),
        "bloodPressure": _blood_pressure_summary(rows),
    }
    return {key: value for key, value in summary.items() if value is not None}


# --------------------------------------------------------------------------- #
# 运动记录
# --------------------------------------------------------------------------- #


def _exercise_item(row: RecordTable) -> dict[str, Any] | None:
    try:
        from ..exercises.service import exercise_from_row
    except Exception:  # noqa: BLE001 - G3 未完成时退回原始 payload
        exercise_from_row = None
    if exercise_from_row is not None:
        try:
            exercise = exercise_from_row(row)
            if exercise is not None:
                return {
                    "activity": exercise.activity,
                    "durationSec": exercise.durationSec,
                    "distanceKm": exercise.distanceKm,
                    "intensity": exercise.intensity,
                    "subjective": exercise.subjective,
                    "startAt": exercise.startAt.isoformat(),
                }
        except Exception:  # noqa: BLE001, S110 - 坏 payload 回退到原始字段解析
            pass
    payload = row.payload or {}
    activity = payload.get("activity")
    duration = _number(payload.get("durationSec"))
    if not isinstance(activity, str) or duration is None or duration <= 0:
        return None
    return {
        "activity": activity,
        "durationSec": int(duration),
        "distanceKm": _number(payload.get("distanceKm")),
        "intensity": payload.get("intensity"),
        "subjective": payload.get("subjective"),
        "startAt": str(payload.get("startAt") or row.captured_at.isoformat()),
    }


def _exercises(session: Session, member_id: str) -> list[dict[str, Any]]:
    rows = _recent_rows(session, member_id, (EXERCISE_TYPE,), limit=20)
    items = [item for row in rows if (item := _exercise_item(row)) is not None]
    return items[:10]


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #


def build_coach_context(
    session: Session,
    *,
    member_id: str | None = None,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同步汇总教练上下文；天气由调用方（异步 API）传入。"""
    if not member_id:
        from ..db.repositories import ensure_default_member

        member_id = ensure_default_member(session).id
    member = _member(session, member_id)
    return {
        "memberId": member_id,
        "generatedAt": utc_now().isoformat(),
        "windowDays": WINDOW_DAYS,
        "scores": _score_report(session, member_id),
        "health": _health_summary(session, member_id, member),
        "exercises": _exercises(session, member_id),
        "memory": _memory_context(),
        "weather": weather,
    }


# --------------------------------------------------------------------------- #
# 给系统提示渲染的紧凑文本
# --------------------------------------------------------------------------- #


def _score_lines(scores: dict[str, Any] | None) -> list[str]:
    if not isinstance(scores, dict):
        return []
    overall = scores.get("overall")
    grade = GRADE_LABELS.get(str(scores.get("grade") or "unknown"), "未知")
    lines = [f"总分 {overall}/100（{grade}）" if overall is not None else "暂无总分"]
    for category in scores.get("categories") or []:
        if not isinstance(category, dict):
            continue
        label = category.get("label") or category.get("id") or "项目"
        score = category.get("score")
        cat_grade = GRADE_LABELS.get(str(category.get("grade") or "unknown"), "未知")
        factors = [str(item) for item in category.get("factors") or [] if item]
        suffix = f"；依据：{'、'.join(factors[:3])}" if factors else ""
        lines.append(f"- {label}：{score}（{cat_grade}）{suffix}")
    missing = scores.get("missing") or []
    if missing:
        lines.append(f"缺失项：{'、'.join(str(item) for item in missing)}")
    return lines


def _health_lines(health: dict[str, Any] | None) -> list[str]:
    if not isinstance(health, dict) or not health:
        return []
    lines: list[str] = []
    steps = health.get("steps")
    if isinstance(steps, dict):
        lines.append(
            f"步数：日均 {steps.get('dailyAverage')} 步"
            f"（{steps.get('days')} 天有数据，最近一天 {steps.get('latest')} 步）"
        )
    heart = health.get("heartRate")
    if isinstance(heart, dict):
        if heart.get("average") is not None:
            text = (
                f"心率：平均 {heart.get('average')} bpm"
                f"（{heart.get('min')}–{heart.get('max')} bpm，{heart.get('samples')} 个样本）"
            )
        else:
            text = "心率：暂无记录样本"
        if heart.get("restingBpm") is not None:
            text += f"；档案静息心率 {heart.get('restingBpm')} bpm"
        lines.append(text)
    sleep = health.get("sleep")
    if isinstance(sleep, dict):
        lines.append(
            f"睡眠：日均 {sleep.get('averageHours')} 小时"
            f"（{sleep.get('days')} 天有数据，最近一晚 {sleep.get('latestHours')} 小时）"
        )
    weight = health.get("weight")
    if isinstance(weight, dict):
        lines.append(f"体重：{weight.get('value')} {weight.get('unit') or 'kg'}")
    pressure = health.get("bloodPressure")
    if isinstance(pressure, dict):
        lines.append(
            f"血压：{pressure.get('systolic')}/{pressure.get('diastolic')} "
            f"{pressure.get('unit') or 'mmHg'}"
        )
    return lines


def _exercise_lines(exercises: Any) -> list[str]:
    if not isinstance(exercises, list):
        return []
    lines: list[str] = []
    for item in exercises[:5]:
        if not isinstance(item, dict):
            continue
        activity = ACTIVITY_LABELS.get(str(item.get("activity")), str(item.get("activity")))
        duration = _number(item.get("durationSec"))
        minutes = round(duration / 60) if duration else None
        parts = [activity]
        if minutes is not None:
            parts.append(f"{minutes} 分钟")
        distance = _number(item.get("distanceKm"))
        if distance is not None:
            parts.append(f"{_round(distance)} km")
        intensity = INTENSITY_LABELS.get(str(item.get("intensity")))
        if intensity:
            parts.append(intensity)
        subjective = item.get("subjective")
        if subjective:
            parts.append(f"主观感受{subjective}")
        start = str(item.get("startAt") or "")[:10]
        lines.append(f"- {start} {'，'.join(parts)}")
    return lines


def _weather_lines(weather: Any) -> list[str]:
    if not isinstance(weather, dict):
        return []
    days = weather.get("days")
    if not isinstance(days, list) or not days:
        return []
    lines: list[str] = []
    for day in days[:3]:
        if not isinstance(day, dict):
            continue
        precip = day.get("precipitationProbability")
        text = (
            f"- {day.get('date')}：{day.get('tempMin')}–{day.get('tempMax')}°C"
            f"，降水概率 {precip if precip is not None else '—'}%"
        )
        if day.get("weatherCode") is not None:
            text += f"（天气代码 {day.get('weatherCode')}）"
        lines.append(text)
    return lines


def render_coach_context(context: dict[str, Any] | None) -> str:
    """把上下文渲染成系统提示里的紧凑中文片段；缺失段落直接省略。"""
    if not isinstance(context, dict):
        return "（暂无教练上下文数据）"

    sections: list[str] = []
    score_lines = _score_lines(context.get("scores"))
    if score_lines:
        sections.append("【评分】\n" + "\n".join(score_lines))
    health_lines = _health_lines(context.get("health"))
    if health_lines:
        sections.append("【最近 7 天健康数据】\n" + "\n".join(f"- {line}" for line in health_lines))
    exercise_lines = _exercise_lines(context.get("exercises"))
    if exercise_lines:
        sections.append("【最近运动记录】\n" + "\n".join(exercise_lines))
    memory = context.get("memory")
    if isinstance(memory, dict) and isinstance(memory.get("content"), str) and memory["content"].strip():
        sections.append("【个人记忆（用户已允许助手使用）】\n" + memory["content"].strip())
    weather_lines = _weather_lines(context.get("weather"))
    if weather_lines:
        city = ""
        if isinstance(context.get("weather"), dict):
            city = str(context["weather"].get("city") or "")
        sections.append(f"【天气{f' · {city}' if city else ''}】\n" + "\n".join(weather_lines))
    return "\n\n".join(sections) if sections else "（暂无教练上下文数据）"


__all__ = ["build_coach_context", "render_coach_context"]

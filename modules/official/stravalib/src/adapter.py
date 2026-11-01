"""Stravalib 适配层：把 Strava activity JSON 规范化为本地活动记录与周汇总。

纯函数、无网络、无上游导入，便于单测与复用。所有输出带非诊断声明。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"

_SPORT_KEYS = ("sport_type", "type", "sport")


def _number(value: Any, field: str, *, required: bool = False) -> float | None:
    if value is None:
        if required:
            raise ValueError(f"{field} 缺失")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 必须是数字")
    return float(value)


def _text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} 缺失")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip()


def _iso(value: Any, field: str) -> str:
    text = _text(value, field, required=True)
    assert text is not None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} 不是 ISO 8601 时间") from exc
    return parsed.isoformat()


def normalize_activity(raw: Any) -> dict[str, Any]:
    """规范化单条 Strava activity；字段缺失时抛 ``ValueError``。"""
    if not isinstance(raw, dict):
        raise TypeError("activity 必须是对象")
    activity_id = raw.get("id")
    if activity_id is None:
        raise ValueError("id 缺失")
    if isinstance(activity_id, bool) or not isinstance(activity_id, (str, int)):
        raise TypeError("id 必须是字符串或整数")
    sport = None
    for key in _SPORT_KEYS:
        sport = _text(raw.get(key), key)
        if sport:
            break
    if sport is None:
        raise ValueError("sport_type/type 缺失")
    start = _iso(raw.get("start_date") or raw.get("start_date_local"), "start_date")
    distance = _number(raw.get("distance"), "distance", required=True) or 0.0
    moving = _number(raw.get("moving_time"), "moving_time", required=True) or 0.0
    if distance < 0 or moving < 0:
        raise ValueError("distance/moving_time 不能为负")
    return {
        "id": str(activity_id),
        "name": str(raw.get("name") or "").strip()[:200],
        "sport": sport[:64],
        "startDate": start,
        "distanceM": round(distance, 1),
        "distanceKm": round(distance / 1000.0, 3),
        "movingTimeS": int(moving),
        "avgHeartRate": _number(raw.get("average_heartrate"), "average_heartrate"),
        "maxHeartRate": _number(raw.get("max_heartrate"), "max_heartrate"),
    }


def normalize_activities(rows: Any) -> dict[str, Any]:
    """规范化活动数组，按开始时间倒序；非数组输入抛 ``ValueError``。"""
    if not isinstance(rows, list):
        raise TypeError("activities 必须是数组")
    items = [normalize_activity(item) for item in rows]
    items.sort(key=lambda item: item["startDate"], reverse=True)
    return {"activities": items, "count": len(items), "disclaimer": DISCLAIMER}


def _week_key(start_date: str) -> tuple[str, str]:
    parsed = datetime.fromisoformat(start_date)
    year, week, _ = parsed.isocalendar()
    monday = parsed.date().fromordinal(parsed.date().toordinal() - parsed.weekday())
    return f"{year}-W{week:02d}", monday.isoformat()


def weekly_summary(rows: Any) -> dict[str, Any]:
    """按 ISO 周汇总距离/时长/活动数，返回图表可直接消费的 series。"""
    normalized = normalize_activities(rows)
    buckets: dict[str, dict[str, Any]] = {}
    for item in normalized["activities"]:
        key, monday = _week_key(item["startDate"])
        bucket = buckets.setdefault(
            key,
            {
                "week": key,
                "weekStart": monday,
                "distanceKm": 0.0,
                "movingTimeS": 0,
                "activityCount": 0,
                "heartRateSum": 0.0,
                "heartRateCount": 0,
            },
        )
        bucket["distanceKm"] += item["distanceKm"]
        bucket["movingTimeS"] += item["movingTimeS"]
        bucket["activityCount"] += 1
        if item["avgHeartRate"] is not None:
            bucket["heartRateSum"] += item["avgHeartRate"]
            bucket["heartRateCount"] += 1
    weeks = []
    for bucket in sorted(buckets.values(), key=lambda item: item["weekStart"]):
        count = bucket["heartRateCount"]
        weeks.append(
            {
                "week": bucket["week"],
                "weekStart": bucket["weekStart"],
                "distanceKm": round(bucket["distanceKm"], 2),
                "movingHours": round(bucket["movingTimeS"] / 3600.0, 2),
                "activityCount": bucket["activityCount"],
                "avgHeartRate": round(bucket["heartRateSum"] / count, 1) if count else None,
            }
        )
    return {
        "weeks": weeks,
        "series": [{"week": item["week"], "distanceKm": item["distanceKm"]} for item in weeks],
        "totalDistanceKm": round(sum(item["distanceKm"] for item in weeks), 2),
        "totalMovingHours": round(sum(item["movingHours"] for item in weeks), 2),
        "activityCount": normalized["count"],
        "disclaimer": DISCLAIMER,
    }

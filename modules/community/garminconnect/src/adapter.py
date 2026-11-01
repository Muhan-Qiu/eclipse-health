"""Garmin Connect 原始 JSON 的纯函数归一化。

不 import 上游 garminconnect，便于单测；不接触凭据日志。字段名以
python-garminconnect 的 REST 返回为准，缺失字段给安全默认值。
"""

from __future__ import annotations

from typing import Any

_MAX_TEXT = 200


class GarminAdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any, limit: int = _MAX_TEXT) -> str:
    return str(value or "")[:limit]


def build_login(params: dict[str, Any]) -> dict[str, str]:
    """提取登录凭据；只返回给上游调用，不写日志、不落盘。"""
    if not isinstance(params, dict):
        raise GarminAdapterError("invalid_input", "params 必须是对象")
    email = params.get("email")
    password = params.get("password")
    if not isinstance(email, str) or not email.strip():
        raise GarminAdapterError("invalid_input", "params.email 必须是非空字符串")
    if not isinstance(password, str) or not password:
        raise GarminAdapterError("invalid_input", "params.password 必须是非空字符串")
    return {"email": email.strip()[:200], "password": password[:200]}


def normalize_activity(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GarminAdapterError("invalid_activity", "活动必须是对象")
    activity_id = raw.get("activityId")
    if activity_id is None:
        raise GarminAdapterError("invalid_activity", "活动缺少 activityId")
    activity_type = raw.get("activityType")
    if isinstance(activity_type, dict):
        activity_type = activity_type.get("typeKey") or activity_type.get("typeId")
    payload: dict[str, Any] = {
        "activityId": activity_id,
        "activityType": _text(activity_type or "unknown", 64),
        "name": _text(raw.get("activityName") or ""),
        "startTime": _text(raw.get("startTimeLocal") or raw.get("startTimeGMT") or "", 64),
    }
    for source, target in (
        ("duration", "durationSeconds"),
        ("distance", "distanceMeters"),
        ("averageHR", "averageHeartRate"),
        ("calories", "calories"),
    ):
        number = _number(raw.get(source))
        if number is not None:
            payload[target] = number
    return payload


def normalize_sleep(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GarminAdapterError("invalid_sleep", "睡眠数据必须是对象")
    dto = raw.get("dailySleepDTO") if isinstance(raw.get("dailySleepDTO"), dict) else raw
    total = _number(dto.get("sleepTimeSeconds"))
    if total is None or total < 0:
        raise GarminAdapterError("invalid_sleep", "睡眠数据缺少 sleepTimeSeconds")
    result: dict[str, Any] = {
        "start": _text(dto.get("sleepStartTimestampGMT") or dto.get("calendarDate") or "", 64),
        "end": _text(dto.get("sleepEndTimestampGMT") or dto.get("calendarDate") or "", 64),
        "totalSleepSeconds": total,
    }
    for source, target in (
        ("deepSleepSeconds", "deepSleepSeconds"),
        ("lightSleepSeconds", "lightSleepSeconds"),
        ("remSleepSeconds", "remSleepSeconds"),
        ("awakeSleepSeconds", "awakeSeconds"),
    ):
        number = _number(dto.get(source))
        if number is not None:
            result[target] = number
    return result


def normalize_body(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GarminAdapterError("invalid_body", "身体成分必须是对象")
    average = raw.get("totalAverage") if isinstance(raw.get("totalAverage"), dict) else {}
    samples = raw.get("dateWeightList")
    if not average and isinstance(samples, list) and samples:
        average = samples[0] if isinstance(samples[0], dict) else {}
    date = raw.get("startDate") or average.get("calendarDate") or average.get("date") or ""
    result: dict[str, Any] = {"date": _text(date, 64)}
    for source, target in (
        ("weight", "weightKg"),
        ("bmi", "bmi"),
        ("bodyFat", "bodyFatPercent"),
        ("bodyWater", "bodyWaterPercent"),
        ("muscleMass", "muscleMassKg"),
    ):
        number = _number(average.get(source))
        if number is not None:
            # Garmin 体重单位是克
            result[target] = round(number / 1000.0, 3) if target == "weightKg" else number
    return result


def summarize(activities: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(activities, list):
        raise GarminAdapterError("invalid_input", "activities 必须是数组")
    distance_m = sum(float(item.get("distanceMeters") or 0) for item in activities)
    duration_s = sum(float(item.get("durationSeconds") or 0) for item in activities)
    return {
        "activities": len(activities),
        "distanceKm": round(distance_m / 1000.0, 3),
        "durationMinutes": round(duration_s / 60.0, 1),
    }

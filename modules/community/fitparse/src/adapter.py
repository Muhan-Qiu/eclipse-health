"""python-fitparse 记录映射与统计（纯函数）。不导入 fitparse，便于单测。"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

_MAX_HEART_RATE = 300
_MAX_SPEED_MPS = 40.0
_SEMICIRCLE_SCALE = 180.0 / (2**31)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def semicircles_to_degrees(value: Any) -> float | None:
    """FIT 位置使用半圆；已是度数的输入原样返回。"""
    number = _number(value)
    if number is None or abs(number) > 2**31:
        return None
    if abs(number) <= 180:
        return round(number, 7)
    return round(number * _SEMICIRCLE_SCALE, 7)


def record_from_fitparse(fields: dict[str, Any]) -> dict[str, Any]:
    """把 ``record.get_values()`` 的结果整理为稳定结构。"""
    if not isinstance(fields, dict):
        raise TypeError("FIT record 必须是对象")
    heart_rate = _number(fields.get("heart_rate"))
    if heart_rate is not None and not 20 <= heart_rate <= _MAX_HEART_RATE:
        heart_rate = None
    speed = _number(fields.get("enhanced_speed"))
    if speed is None:
        speed = _number(fields.get("speed"))
    if speed is not None and not 0 <= speed <= _MAX_SPEED_MPS:
        speed = None
    altitude = _number(fields.get("enhanced_altitude"))
    if altitude is None:
        altitude = _number(fields.get("altitude"))
    return {
        "timestamp": _iso(fields.get("timestamp")),
        "heartRate": heart_rate,
        "speedMps": speed,
        "distanceM": _number(fields.get("distance")),
        "altitudeM": altitude,
        "cadence": _number(fields.get("cadence")),
        "latitude": semicircles_to_degrees(fields.get("position_lat")),
        "longitude": semicircles_to_degrees(fields.get("position_long")),
    }


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        first = datetime.fromisoformat(start)
        last = datetime.fromisoformat(end)
        seconds = (last - first).total_seconds()
    except (TypeError, ValueError):
        return None
    return round(seconds, 3) if seconds >= 0 else None


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(records, list) or not records:
        raise ValueError("没有可用的 FIT record")
    heart_rates = [item["heartRate"] for item in records if item.get("heartRate") is not None]
    timestamps = [item["timestamp"] for item in records if item.get("timestamp")]
    distance = None
    for item in reversed(records):
        if item.get("distanceM") is not None:
            distance = float(item["distanceM"])
            break
    coverage = len(heart_rates) / len(records)
    return {
        "samples": len(records),
        "startedAt": timestamps[0] if timestamps else None,
        "endedAt": timestamps[-1] if timestamps else None,
        "durationSeconds": _duration_seconds(
            timestamps[0] if timestamps else None,
            timestamps[-1] if timestamps else None,
        ),
        "distanceKm": None if distance is None else round(distance / 1000.0, 3),
        "avgHeartRate": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
        "maxHeartRate": max(heart_rates) if heart_rates else None,
        "heartRateCoverage": round(coverage, 3),
        "quality": "good" if coverage >= 0.8 else "partial" if coverage >= 0.3 else "poor",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def session_payload(summary: dict[str, Any], laps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "startedAt": summary.get("startedAt"),
        "endedAt": summary.get("endedAt"),
        "durationSeconds": summary.get("durationSeconds"),
        "distanceKm": summary.get("distanceKm"),
        "avgHeartRate": summary.get("avgHeartRate"),
        "maxHeartRate": summary.get("maxHeartRate"),
        "source": "fitparse",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    if laps:
        payload["laps"] = laps[:64]
    return payload

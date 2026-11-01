"""Dexcom 血糖读数映射与统计（纯函数）。不导入 pydexcom，便于单测。"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

MGDL_PER_MMOL = 18.0182
TREND_TEXT = {
    0: "none",
    1: "doubleUp",
    2: "singleUp",
    3: "fortyFiveUp",
    4: "flat",
    5: "fortyFiveDown",
    6: "singleDown",
    7: "doubleDown",
    8: "notComputable",
    9: "rateOutOfRange",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _trend(raw: Any) -> tuple[int | str | None, str]:
    direction = raw.get("trend_direction") if isinstance(raw, dict) else None
    value = raw.get("trend") if isinstance(raw, dict) else None
    if isinstance(value, bool):
        value = None
    if isinstance(value, (int, float)):
        trend: int | str | None = int(value)
        return trend, TREND_TEXT.get(trend, "unknown")
    if isinstance(value, str) and value:
        return value, value
    if isinstance(direction, str) and direction:
        return direction, direction
    return None, "unknown"


def normalize_reading(raw: dict[str, Any]) -> dict[str, Any]:
    """接受 mg/dL 或 mmol/L 字段，统一输出两者并做范围校验。"""
    if not isinstance(raw, dict):
        raise TypeError("血糖读数必须是对象")
    mgdl = _number(raw.get("valueMgdl"))
    if mgdl is None:
        mgdl = _number(raw.get("value"))
    mmol = _number(raw.get("valueMmol"))
    if mmol is None:
        mmol = _number(raw.get("mmol_l"))
    if mgdl is None and mmol is None:
        raise ValueError("血糖读数缺少数值")
    if mmol is None and mgdl is not None:
        mmol = mgdl / MGDL_PER_MMOL
    if mgdl is None and mmol is not None:
        mgdl = mmol * MGDL_PER_MMOL
    assert mgdl is not None and mmol is not None
    if not 10 <= mgdl <= 800:
        raise ValueError("血糖值超出 10..800 mg/dL")
    trend, trend_text = _trend(raw)
    measured_at = _iso(
        raw.get("measuredAt") or raw.get("timestamp") or raw.get("datetime")
    )
    return {
        "valueMgdl": round(mgdl, 1),
        "valueMmol": round(mmol, 1),
        "trend": trend,
        "trendText": trend_text,
        "measuredAt": measured_at,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def summarize_readings(readings: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(readings, list) or not readings:
        raise ValueError("没有血糖读数")
    normalized = [normalize_reading(item) for item in readings]
    values = [item["valueMgdl"] for item in normalized]
    latest = normalized[-1]
    dated = [item for item in normalized if item.get("measuredAt")]
    if dated:
        latest = max(dated, key=lambda item: str(item["measuredAt"]))
    in_range = sum(1 for value in values if 70 <= value <= 180)
    return {
        "samples": len(normalized),
        "avgMgdl": round(sum(values) / len(values), 1),
        "minMgdl": min(values),
        "maxMgdl": max(values),
        "timeInRangePercent": round(in_range / len(values) * 100, 1),
        "lowCount": sum(1 for value in values if value < 70),
        "highCount": sum(1 for value in values if value > 180),
        "latest": latest,
        "unit": "mg/dL",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def to_record(reading: dict[str, Any]) -> dict[str, Any]:
    return {
        "valueMgdl": reading["valueMgdl"],
        "valueMmol": reading["valueMmol"],
        "trend": reading.get("trend"),
        "trendText": reading.get("trendText", "unknown"),
        "measuredAt": reading.get("measuredAt"),
        "source": "dexcom-share",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

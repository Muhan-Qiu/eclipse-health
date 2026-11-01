"""Tremor-inspired KPI adapter: cards, deltas and progress.

Pure functions; no React or upstream Tremor code is imported.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"


def _number(value: Any, field: str, *, required: bool = False) -> float | None:
    if value is None:
        if required:
            raise ValueError(f"{field} 缺失")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 必须是数字")
    return float(value)


def _build_card(metric: Any, index: int) -> dict[str, Any]:
    if not isinstance(metric, dict):
        raise TypeError(f"metrics[{index}] 必须是对象")
    label = metric.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"metrics[{index}].label 缺失")
    value = _number(metric.get("value"), f"metrics[{index}].value", required=True)
    previous = _number(metric.get("previous"), f"metrics[{index}].previous")
    delta = None
    percent = None
    direction = "flat"
    if previous is not None and value is not None:
        delta = round(value - previous, 3)
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        if previous != 0:
            percent = round((value - previous) / abs(previous) * 100.0, 2)
    progress = None
    low = _number(metric.get("min"), f"metrics[{index}].min")
    high = _number(metric.get("max"), f"metrics[{index}].max")
    if low is not None and high is not None and high > low and value is not None:
        ratio = (value - low) / (high - low)
        progress = {"min": low, "max": high, "ratio": round(max(0.0, min(1.0, ratio)), 4)}
    return {
        "id": str(metric.get("id") or f"kpi-{index + 1}")[:64],
        "label": label.strip()[:80],
        "value": value,
        "unit": str(metric.get("unit") or "")[:32],
        "previous": previous,
        "delta": delta,
        "deltaPercent": percent,
        "direction": direction,
        "progress": progress,
    }


def build_kpis(metrics: Any) -> dict[str, Any]:
    """把任意指标数组转成 KPI 卡片；空数组是合法的首次运行状态。"""
    if metrics is None:
        metrics = []
    if not isinstance(metrics, list):
        raise TypeError("metrics 必须是数组")
    cards = [_build_card(item, index) for index, item in enumerate(metrics)]
    return {
        "cards": cards,
        "headline": cards[0] if cards else None,
        "count": len(cards),
        "disclaimer": DISCLAIMER,
    }


def summarize(values: Any) -> dict[str, Any]:
    if values is None:
        values = []
    if not isinstance(values, list):
        raise TypeError("values 必须是数组")
    data = [_number(item, "values", required=True) for item in values]
    numbers = [item for item in data if item is not None]
    return {
        "count": len(numbers),
        "min": min(numbers) if numbers else None,
        "max": max(numbers) if numbers else None,
        "mean": round(sum(numbers) / len(numbers), 3) if numbers else None,
        "disclaimer": DISCLAIMER,
    }

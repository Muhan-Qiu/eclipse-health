"""uPlot-inspired trend adapter: normalize/downsample time series.

Pure functions only; no upstream JS is imported or bundled.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
DEFAULT_MAX_POINTS = 600


def _coerce_point(item: Any) -> tuple[float, float]:
    if isinstance(item, dict):
        raw_t = item.get("t", item.get("time", item.get("x")))
        raw_v = item.get("v", item.get("value", item.get("y")))
    elif isinstance(item, (list, tuple)) and len(item) == 2:
        raw_t, raw_v = item
    else:
        raise ValueError("point 必须是 {t,v} 或 [t,v]")
    for value, field in ((raw_t, "t"), (raw_v, "v")):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"point.{field} 必须是数字")
    return float(raw_t), float(raw_v)


def _unit(value: Any) -> str:
    text = str(value or "").strip()
    return text[:32]


def downsample(points: list[dict[str, float]], max_points: int) -> list[dict[str, float]]:
    """按等步长抽取，保留首尾点；``max_points`` 至少为 2。"""
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points < 2:
        raise ValueError("maxPoints 必须是 >=2 的整数")
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    picked = [points[round(index * step)] for index in range(max_points)]
    picked[-1] = points[-1]
    return picked


def normalize_series(
    items: Any,
    *,
    unit: str = "",
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any]:
    """校验、排序、去重、降采样，返回 sparkline/table 可直接消费的结构。"""
    if items is None:
        items = []
    if not isinstance(items, list):
        raise TypeError("points 必须是数组")
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points < 2:
        raise ValueError("maxPoints 必须是 >=2 的整数")
    by_time: dict[float, float] = {}
    for item in items:
        t, v = _coerce_point(item)
        by_time[t] = v
    ordered = [{"t": t, "v": by_time[t]} for t in sorted(by_time)]
    sampled = downsample(ordered, max_points)
    latest = sampled[-1] if sampled else None
    values = [point["v"] for point in sampled]
    return {
        "points": sampled,
        "latest": {"t": latest["t"], "value": latest["v"]} if latest else None,
        "count": len(sampled),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "mean": round(sum(values) / len(values), 3) if values else None,
        "unit": _unit(unit),
        "disclaimer": DISCLAIMER,
    }


def summarize(items: Any, *, unit: str = "") -> dict[str, Any]:
    """轻量统计；空输入返回零值而不是报错（首次运行场景）。"""
    result = normalize_series(items, unit=unit, max_points=DEFAULT_MAX_POINTS)
    return {
        "count": result["count"],
        "min": result["min"],
        "max": result["max"],
        "mean": result["mean"],
        "latest": result["latest"],
        "unit": result["unit"],
        "disclaimer": DISCLAIMER,
    }

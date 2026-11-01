"""Observable Plot-inspired adapter: trend, histogram and quantile summaries.

Pure Python; upstream JavaScript/D3 is neither bundled nor executed.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
MAX_BINS = 32


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 必须是数字")
    return float(value)


def _values(values: Any) -> list[float]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise TypeError("values 必须是数组")
    return [_number(item, "values") for item in values]


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise ValueError("空数组没有分位数")
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _point(item: Any) -> tuple[Any, float]:
    if isinstance(item, dict):
        label = item.get("x", item.get("label", item.get("t", item.get("time"))))
        value = item.get("y", item.get("value", item.get("v")))
    elif isinstance(item, (list, tuple)) and len(item) == 2:
        label, value = item
    else:
        raise ValueError("point 必须是 {x,value} 或 [x,value]")
    if label is None or isinstance(label, bool):
        raise ValueError("point.x 缺失")
    return label, _number(value, "point.value")


def trend(points: Any, *, unit: str = "") -> dict[str, Any]:
    if points is None:
        points = []
    if not isinstance(points, list):
        raise TypeError("points 必须是数组")
    parsed = [_point(item) for item in points]
    labels = [item[0] for item in parsed]
    values = [item[1] for item in parsed]
    return {
        "kind": "line",
        "labels": labels,
        "values": values,
        "latest": {"x": labels[-1], "value": values[-1]} if values else None,
        "count": len(values),
        "unit": str(unit)[:32],
        "disclaimer": DISCLAIMER,
    }


def histogram(values: Any, bins: int = 10) -> dict[str, Any]:
    data = _values(values)
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= MAX_BINS:
        raise ValueError(f"bins 必须是 1..{MAX_BINS} 的整数")
    if not data:
        return {"items": [], "count": 0, "bins": bins, "disclaimer": DISCLAIMER}
    low, high = min(data), max(data)
    if low == high:
        item = {"label": f"{low:g}", "count": len(data), "from": low, "to": high}
        return {"items": [item], "count": len(data), "bins": 1, "disclaimer": DISCLAIMER}
    width = (high - low) / bins
    counts = [0] * bins
    for value in data:
        counts[min(int((value - low) / width), bins - 1)] += 1
    items = [
        {
            "label": f"{low + index * width:.3g}–{low + (index + 1) * width:.3g}",
            "count": counts[index],
            "from": round(low + index * width, 6),
            "to": round(low + (index + 1) * width, 6),
        }
        for index in range(bins)
    ]
    return {"items": items, "count": len(data), "bins": bins, "disclaimer": DISCLAIMER}


def summary(values: Any) -> dict[str, Any]:
    data = sorted(_values(values))
    if not data:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "q1": None,
            "q3": None,
            "disclaimer": DISCLAIMER,
        }
    return {
        "count": len(data),
        "min": data[0],
        "max": data[-1],
        "mean": round(sum(data) / len(data), 3),
        "median": round(_quantile(data, 0.5), 3),
        "q1": round(_quantile(data, 0.25), 3),
        "q3": round(_quantile(data, 0.75), 3),
        "disclaimer": DISCLAIMER,
    }

"""ECharts-inspired chart adapter: build declarative specs without upstream JS.

Only numeric inputs are inspected; nothing from Apache ECharts is bundled or
imported. Specs use a small, renderer-agnostic shape so the core can map them
onto controlled widgets now and richer bar/line views later.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
MAX_BINS = 32


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} 必须是数字")
    return float(value)


def _numbers(values: Any, field: str = "values") -> list[float]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise TypeError(f"{field} 必须是数组")
    return [_number(item, field) for item in values]


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


def build_line_spec(
    points: Any,
    *,
    label: str = "value",
    unit: str = "",
    x_label: str = "time",
) -> dict[str, Any]:
    if not isinstance(points, list):
        raise TypeError("points 必须是数组")
    parsed = [_point(item) for item in points]
    labels = [item[0] for item in parsed]
    values = [item[1] for item in parsed]
    latest = {"x": labels[-1], "value": values[-1]} if values else None
    return {
        "kind": "line",
        "xLabel": str(x_label)[:64],
        "yLabel": str(label)[:64],
        "unit": str(unit)[:32],
        "labels": labels,
        "series": [{"name": str(label)[:64], "data": values}],
        "latest": latest,
        "count": len(values),
        "disclaimer": DISCLAIMER,
    }


def build_bar_spec(
    categories: Any,
    values: Any,
    *,
    label: str = "count",
    unit: str = "",
) -> dict[str, Any]:
    if not isinstance(categories, list):
        raise TypeError("categories 必须是数组")
    data = _numbers(values)
    if len(categories) != len(data):
        raise ValueError("categories 与 values 长度不一致")
    names = [str(item)[:64] for item in categories]
    return {
        "kind": "bar",
        "xLabel": "category",
        "yLabel": str(label)[:64],
        "unit": str(unit)[:32],
        "labels": names,
        "series": [{"name": str(label)[:64], "data": data}],
        "count": len(data),
        "disclaimer": DISCLAIMER,
    }


def distribution(values: Any, bins: int = 10) -> dict[str, Any]:
    """等宽直方图；全空或全等值时给出安全结果。"""
    data = _numbers(values)
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= MAX_BINS:
        raise ValueError(f"bins 必须是 1..{MAX_BINS} 的整数")
    if not data:
        return {"bins": bins, "items": [], "count": 0, "disclaimer": DISCLAIMER}
    low, high = min(data), max(data)
    if low == high:
        items = [{"label": f"{low:g}", "count": len(data), "from": low, "to": high}]
        return {"bins": 1, "items": items, "count": len(data), "disclaimer": DISCLAIMER}
    width = (high - low) / bins
    counts = [0] * bins
    for value in data:
        index = min(int((value - low) / width), bins - 1)
        counts[index] += 1
    items = [
        {
            "label": f"{low + index * width:.3g}–{low + (index + 1) * width:.3g}",
            "count": counts[index],
            "from": round(low + index * width, 6),
            "to": round(low + (index + 1) * width, 6),
        }
        for index in range(bins)
    ]
    return {"bins": bins, "items": items, "count": len(data), "disclaimer": DISCLAIMER}


def summarize(values: Any) -> dict[str, Any]:
    data = _numbers(values)
    return {
        "count": len(data),
        "min": min(data) if data else None,
        "max": max(data) if data else None,
        "mean": round(sum(data) / len(data), 3) if data else None,
        "disclaimer": DISCLAIMER,
    }

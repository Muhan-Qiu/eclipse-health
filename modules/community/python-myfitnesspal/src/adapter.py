"""MyFitnessPal 日记适配层：纯函数解析/映射，便于单测。

不含网络与上游 import；凭据与抓取只在 ``main.py`` 的 ``fetch`` 中处理。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "myfitnesspal"
MAX_ENTRIES = 2000
MEALS = ("breakfast", "lunch", "dinner", "snacks")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MEAL_ALIASES = {
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "snacks": "snacks",
    "snack": "snacks",
}


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require_date(value: Any, field: str = "date") -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise AdapterError(f"{field} 必须是 YYYY-MM-DD 日期")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise AdapterError(f"{field} 不是合法日期") from exc
    return value


def _optional_number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{field} 必须是数字")
    if value < 0:
        raise AdapterError(f"{field} 不能为负数")
    return float(value)


def _meal_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("meal 缺失")
    key = value.strip().lower()
    return _MEAL_ALIASES.get(key, key[:32])


def normalize_entry(entry: Any, day: str, meal: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise AdapterError("日记条目必须是对象")
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AdapterError("条目 name 缺失")
    payload = {
        "capturedAt": f"{require_date(day)}T00:00:00Z",
        "name": name.strip()[:200],
        "meal": _meal_name(meal),
        "calories": _optional_number(entry.get("calories"), "calories"),
        "proteinG": _optional_number(entry.get("proteinG"), "proteinG"),
        "carbsG": _optional_number(entry.get("carbsG"), "carbsG"),
        "fatG": _optional_number(entry.get("fatG"), "fatG"),
        "source": SOURCE,
    }
    return {"recordType": "nutrition.entry", "payload": payload, "note": DISCLAIMER}


def normalize_diary(payload: Any) -> list[dict[str, Any]]:
    """把 ``{"date": ..., "meals": {...}}`` 映射为 nutrition.entry 记录。"""
    if not isinstance(payload, dict):
        raise AdapterError("payload 必须是对象")
    day = require_date(payload.get("date"))
    meals = payload.get("meals")
    if not isinstance(meals, dict):
        raise AdapterError("payload.meals 必须是对象")
    records: list[dict[str, Any]] = []
    for meal, entries in meals.items():
        if not isinstance(entries, list):
            raise AdapterError(f"meals.{meal} 必须是数组")
        for entry in entries:
            records.append(normalize_entry(entry, day, str(meal)))
    if len(records) > MAX_ENTRIES:
        raise AdapterError(f"单日最多导入 {MAX_ENTRIES} 条")
    return records


def summarize_records(records: Any) -> dict[str, Any]:
    """最近一天的热量与宏量营养素合计（数据由调用方传入）。"""
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    by_day: dict[str, dict[str, float]] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        if item.get("recordType") not in (None, "nutrition.entry"):
            continue
        day = str(payload.get("capturedAt") or "")[:10]
        if not day:
            continue
        totals = by_day.setdefault(
            day, {"calories": 0.0, "proteinG": 0.0, "carbsG": 0.0, "fatG": 0.0}
        )
        for field in ("calories", "proteinG", "carbsG", "fatG"):
            value = payload.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[field] += float(value)
    series = [
        {"at": f"{day}T00:00:00Z", "calories": round(totals["calories"], 1)}
        for day, totals in sorted(by_day.items())
    ]
    latest = series[-1] if series else {}
    return {"latest": latest, "series": series[-30:], "note": DISCLAIMER}


def items_for(records: Any) -> dict[str, Any]:
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    items = [
        item["payload"]
        for item in records
        if isinstance(item, dict)
        and item.get("recordType") == "nutrition.entry"
        and isinstance(item.get("payload"), dict)
    ]
    return {"items": items[:200], "count": len(items), "note": DISCLAIMER}

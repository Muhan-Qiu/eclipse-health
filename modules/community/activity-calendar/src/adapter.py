"""Activity-calendar-inspired adapter: daily counts -> heatmap levels.

Pure functions; no React or upstream code is bundled or executed.
Levels follow the familiar 0..4 calendar scale, derived from the busiest day.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
MAX_DAYS = 3660
RECENT_DAYS = 14


def _parse_day(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise TypeError(f"{field} 必须是 YYYY-MM-DD 字符串")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} 不是合法日期") from exc


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} 必须是整数")
    if value < 0:
        raise ValueError(f"{field} 不能为负")
    return value


def _level(count: int, max_count: int) -> int:
    if count <= 0 or max_count <= 0:
        return 0
    return min(4, 1 + int(3 * count / max_count))


def _streaks(counts: list[int]) -> tuple[int, int]:
    longest = 0
    current = 0
    for count in counts:
        if count > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest, current


def build_heatmap(
    counts: Any,
    *,
    days: int = 365,
    today: Any = None,
) -> dict[str, Any]:
    """把 ``{YYYY-MM-DD: count}`` 转成日历热力图数据。"""
    if counts is None:
        raw: dict[str, Any] = {}
    elif isinstance(counts, dict):
        raw = counts
    else:
        raise ValueError("counts 必须是 {date: count} 对象")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days 必须是 1..{MAX_DAYS} 的整数")
    if today is None:
        end = date.today()
    elif isinstance(today, date):
        end = today
    else:
        end = _parse_day(today, "today")
    start = end - timedelta(days=days - 1)

    normalized: dict[date, int] = {}
    for key, value in raw.items():
        day = _parse_day(key, f"counts[{key!r}]")
        normalized[day] = _count(value, f"counts[{key!r}]")

    window = [start + timedelta(days=offset) for offset in range(days)]
    window_counts = [normalized.get(day, 0) for day in window]
    max_count = max(window_counts) if window_counts else 0
    items = [
        {
            "date": day.isoformat(),
            "count": count,
            "level": _level(count, max_count),
        }
        for day, count in zip(window, window_counts, strict=True)
    ]
    longest, current = _streaks(window_counts)
    recent = list(reversed(items[-RECENT_DAYS:]))
    return {
        "days": items,
        "recent": recent,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "activeDays": sum(1 for count in window_counts if count > 0),
        "totalCount": sum(window_counts),
        "maxDayCount": max_count,
        "longestStreak": longest,
        "currentStreak": current,
        "disclaimer": DISCLAIMER,
    }


def summary(counts: Any, *, days: int = 365, today: Any = None) -> dict[str, Any]:
    result = build_heatmap(counts, days=days, today=today)
    return {
        key: result[key]
        for key in (
            "startDate",
            "endDate",
            "activeDays",
            "totalCount",
            "maxDayCount",
            "longestStreak",
            "currentStreak",
            "disclaimer",
        )
    }

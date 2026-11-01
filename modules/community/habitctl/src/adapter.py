"""habitctl 文本输出的纯函数解析与记录映射。

上游 ``habitctl`` 是 Rust CLI，没有稳定的 JSON 输出；本适配层只解析它的文本列表，
格式约定见 README。所有函数不依赖上游二进制，便于单测。
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

_NAME_MAX = 80
_NOTE_MAX = 500

_ENTRY_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\[(?P<mark>[xX ])\]|(?P<glyph>[✔✓✗✘]))\s*(?P<name>.+?)\s*$"
)
_STREAK_RE = re.compile(r"\bstreak\s*[:=]\s*(?P<count>\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class HabitctlError(ValueError):
    """可映射为 INVALID_INPUT / MODULE_ERROR 的适配层错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_habit_list(text: str) -> list[dict[str, Any]]:
    """把 ``habitctl list`` 输出解析成 [{name, done, streak}]。"""
    if not isinstance(text, str):
        raise HabitctlError("invalid_input", "habitctl 输出必须是字符串")
    habits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENTRY_RE.match(line)
        if match is None:
            continue
        raw = match.group("name")
        streak = 0
        streak_match = _STREAK_RE.search(raw)
        if streak_match is not None:
            streak = int(streak_match.group("count"))
            raw = raw[: streak_match.start()]
        name = raw.strip(" -:\t")[:_NAME_MAX]
        if not name or name in seen:
            continue
        seen.add(name)
        mark = (match.group("mark") or "").lower()
        glyph = match.group("glyph") or ""
        done = mark == "x" or bool(glyph) and glyph in "✔✓"
        habits.append({"name": name, "done": done, "streak": streak})
    if not habits:
        raise HabitctlError("empty_habit_list", "未能从 habitctl 输出中解析出任何习惯")
    return habits


def summarize(habits: list[dict[str, Any]]) -> dict[str, Any]:
    """计算今日完成数与最长连续天数；空列表视为错误。"""
    if not habits:
        raise HabitctlError("empty_habit_list", "习惯列表为空")
    valid = [item for item in habits if isinstance(item, dict)]
    if len(valid) != len(habits):
        raise HabitctlError("invalid_habit_list", "习惯列表含非对象项")
    streaks = [int(item.get("streak") or 0) for item in valid]
    return {
        "count": len(valid),
        "doneToday": sum(1 for item in valid if item.get("done") is True),
        "bestStreak": max(streaks) if streaks else 0,
        "totalStreak": sum(streaks),
    }


def build_log_entry(params: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化一次打卡记录。"""
    if not isinstance(params, dict):
        raise HabitctlError("invalid_input", "params 必须是对象")
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HabitctlError("invalid_input", "params.name 必须是非空字符串")
    date = params.get("date")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        raise HabitctlError("invalid_input", "params.date 必须是 YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(date)
    except ValueError as exc:
        raise HabitctlError("invalid_input", "params.date 不是合法日期") from exc
    note = params.get("note") or ""
    if not isinstance(note, str):
        raise HabitctlError("invalid_input", "params.note 必须是字符串")
    return {
        "habit": name.strip()[:_NAME_MAX],
        "date": date,
        "done": bool(params.get("done", True)),
        "note": note[:_NOTE_MAX],
    }


def decorate(habits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给列表项补 UI 用的次要文本。"""
    decorated: list[dict[str, Any]] = []
    for item in habits:
        decorated.append(
            {
                **item,
                "streakText": f"连续 {int(item.get('streak') or 0)} 天",
            }
        )
    return decorated

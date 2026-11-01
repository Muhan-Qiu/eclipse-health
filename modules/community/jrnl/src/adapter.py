"""jrnl ``--export json`` 输出的纯函数解析、搜索与记录映射。

不 import 上游 jrnl；不写日志、不保留绝对路径。所有函数可独立单测。
"""

from __future__ import annotations

import json
from typing import Any

_TITLE_MAX = 200
_BODY_MAX = 20_000


class JournalError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _as_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("entries", "journal", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise JournalError("invalid_export", "jrnl 导出必须是条目数组")


def normalize_entry(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise JournalError("invalid_entry", "日记条目必须是对象")
    title = raw.get("title")
    body = raw.get("body")
    date = raw.get("date")
    if title is None and body is None:
        raise JournalError("invalid_entry", "日记条目缺少 title 与 body")
    tags_raw = raw.get("tags")
    tags: list[str] = []
    if isinstance(tags_raw, list):
        tags = [str(item)[:64] for item in tags_raw if str(item).strip()][:32]
    elif isinstance(tags_raw, str):
        tags = [part.strip()[:64] for part in tags_raw.split(",") if part.strip()][:32]
    return {
        "date": str(date or "")[:64],
        "title": str(title or "")[:_TITLE_MAX],
        "body": str(body or "")[:_BODY_MAX],
        "tags": tags,
        "starred": bool(raw.get("starred", False)),
    }


def parse_export(text: str) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        raise JournalError("invalid_input", "导出内容必须是字符串")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JournalError("invalid_json", "jrnl 导出不是合法 JSON") from exc
    entries = [normalize_entry(item) for item in _as_list(payload)]
    entries.sort(key=lambda item: item["date"], reverse=True)
    return entries


def search(
    entries: list[dict[str, Any]],
    query: str,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        raise JournalError("invalid_input", "query 必须是非空字符串")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise JournalError("invalid_input", "limit 必须是 1..100 的整数")
    needle = query.strip().lower()
    wanted = {str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()}
    matches: list[dict[str, Any]] = []
    for entry in entries:
        haystack = f"{entry.get('title', '')}\n{entry.get('body', '')}".lower()
        if needle not in haystack:
            continue
        entry_tags = {str(tag).lower() for tag in entry.get("tags", [])}
        if wanted and not wanted.issubset(entry_tags):
            continue
        matches.append(entry)
    return matches[:limit]


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(entries, list):
        raise JournalError("invalid_input", "entries 必须是数组")
    tag_counts: dict[str, int] = {}
    for entry in entries:
        for tag in entry.get("tags", []):
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    dates = [entry.get("date", "") for entry in entries if entry.get("date")]
    return {
        "total": len(entries),
        "latestDate": max(dates) if dates else None,
        "tagCounts": dict(sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:20]),
    }


def to_record(entry: dict[str, Any]) -> dict[str, Any]:
    """映射为 ``journal.entry`` 记录 payload。"""
    normalized = normalize_entry(entry)
    return {**normalized, "nonDiagnostic": True}

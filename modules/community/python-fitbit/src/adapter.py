"""Fitbit Web API 适配层：纯函数解析/映射，便于单测。

本文件只依赖标准库；上游 ``fitbit`` 包与网络请求由 ``main.py`` 懒加载。
所有输出均为非诊断数据，附「非医疗器械，不用于诊断」声明。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlencode

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "fitbit"
MAX_RECORDS = 5000

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KINDS = ("activity", "sleep", "body", "heartRate")
AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _require_date(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise AdapterError(f"{field} 必须是 YYYY-MM-DD 日期")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise AdapterError(f"{field} 不是合法日期") from exc
    return value


def parse_date_range(params: dict[str, Any]) -> tuple[str, str]:
    """校验 Fitbit API 日期范围（单次最多 31 天）。"""
    if not isinstance(params, dict):
        raise AdapterError("params 必须是对象")
    start = _require_date(params.get("startDate"), "startDate")
    end = _require_date(params.get("endDate"), "endDate")
    span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    if span < 0:
        raise AdapterError("endDate 不能早于 startDate")
    if span > 31:
        raise AdapterError("Fitbit 单次查询最多 31 天")
    return start, end


def _number(value: Any, field: str, *, minimum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{field} 必须是数字")
    result = float(value)
    if minimum is not None and result < minimum:
        raise AdapterError(f"{field} 不能小于 {minimum:g}")
    return result


def _int(value: Any, field: str, *, minimum: int = 0) -> int | None:
    result = _number(value, field, minimum=float(minimum))
    return None if result is None else int(result)


def _record(record_type: str, payload: dict[str, Any], request_id: str | None) -> dict[str, Any]:
    record: dict[str, Any] = {"recordType": record_type, "payload": payload, "note": DISCLAIMER}
    if request_id:
        record["requestId"] = request_id
    return record


def normalize_activity_day(day: Any, request_id: str | None = None) -> dict[str, Any]:
    if not isinstance(day, dict):
        raise AdapterError("activity 条目必须是对象")
    captured = _require_date(day.get("date") or day.get("dateTime"), "activity.date")
    summary = day.get("summary") if isinstance(day.get("summary"), dict) else day
    active_minutes = None
    parts = [
        summary.get("lightlyActiveMinutes"),
        summary.get("fairlyActiveMinutes"),
        summary.get("veryActiveMinutes"),
    ]
    if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in parts):
        active_minutes = int(sum(parts))
    return _record(
        "activity.session",
        {
            "capturedAt": f"{captured}T00:00:00Z",
            "steps": _int(summary.get("steps"), "steps") or 0,
            "caloriesOut": _number(summary.get("caloriesOut"), "caloriesOut"),
            "activeMinutes": active_minutes,
            "source": SOURCE,
        },
        request_id,
    )


def normalize_sleep_log(log: Any, request_id: str | None = None) -> dict[str, Any]:
    if not isinstance(log, dict):
        raise AdapterError("sleep 条目必须是对象")
    started = log.get("startTime") or log.get("dateOfSleep")
    if not isinstance(started, str) or len(started) < 10:
        raise AdapterError("sleep.startTime 缺失")
    captured_at = started.replace(" ", "T")
    if "T" not in captured_at:
        captured_at = f"{_require_date(started[:10], 'sleep.date')}T00:00:00Z"
    efficiency = _number(log.get("efficiency"), "efficiency")
    if efficiency is not None and efficiency > 100:
        raise AdapterError("efficiency 不能超过 100")
    return _record(
        "sleep.session",
        {
            "capturedAt": captured_at,
            "minutesAsleep": _int(log.get("minutesAsleep"), "minutesAsleep"),
            "minutesInBed": _int(log.get("timeInBed"), "timeInBed"),
            "efficiency": efficiency,
            "source": SOURCE,
        },
        request_id,
    )


def normalize_weight_log(log: Any, request_id: str | None = None) -> dict[str, Any]:
    if not isinstance(log, dict):
        raise AdapterError("weight 条目必须是对象")
    day = _require_date(log.get("date"), "weight.date")
    clock = log.get("time")
    clock = clock if isinstance(clock, str) and clock else "00:00:00"
    weight = _number(log.get("weight", log.get("weightKg")), "weight")
    if weight is None or weight <= 0:
        raise AdapterError("weight 必须是正数（kg）")
    return _record(
        "body.measurement",
        {
            "capturedAt": f"{day}T{clock}Z",
            "weightKg": round(weight, 3),
            "bmi": _number(log.get("bmi"), "bmi"),
            "source": SOURCE,
        },
        request_id,
    )


def normalize_heart_rate_point(point: Any, request_id: str | None = None) -> dict[str, Any]:
    if not isinstance(point, dict):
        raise AdapterError("heartRate 条目必须是对象")
    raw_time = point.get("dateTime") or point.get("time")
    if not isinstance(raw_time, str) or len(raw_time) < 10:
        raise AdapterError("heartRate.dateTime 缺失")
    kind = point.get("value")
    bpm = kind.get("bpm") if isinstance(kind, dict) else kind
    value = _int(bpm, "bpm", minimum=1)
    if value is None:
        raise AdapterError("heartRate 缺少 bpm")
    captured_at = raw_time.replace(" ", "T")
    if not captured_at.endswith("Z"):
        captured_at += "Z"
    return _record(
        "hr.sample",
        {"capturedAt": captured_at, "bpm": value, "source": SOURCE},
        request_id,
    )


_NORMALIZERS = {
    "activity": normalize_activity_day,
    "sleep": normalize_sleep_log,
    "body": normalize_weight_log,
    "heartRate": normalize_heart_rate_point,
}


def _extract_items(payload: dict[str, Any], kind: str) -> list[Any]:
    if kind == "activity":
        items = payload.get("activities", payload.get("activity", payload.get("data")))
        if isinstance(items, dict):
            items = [items]
    elif kind == "sleep":
        items = payload.get("sleep", payload.get("data"))
    elif kind == "body":
        items = payload.get("weight", payload.get("body", payload.get("data")))
    else:
        intraday = payload.get("activities-heart-intraday")
        container = intraday if isinstance(intraday, dict) else payload
        items = container.get("dataset", payload.get("data"))
    if not isinstance(items, list):
        raise AdapterError(f"{kind} payload 缺少记录数组")
    if len(items) > MAX_RECORDS:
        raise AdapterError(f"单次最多导入 {MAX_RECORDS} 条记录")
    return items


def records_from_export(
    payload: dict[str, Any], kind: str, request_id: str | None = None
) -> list[dict[str, Any]]:
    """把 Fitbit API JSON（或离线导出）映射成 eclipse 记录。"""
    if kind not in KINDS:
        raise AdapterError(f"kind 必须是 {', '.join(KINDS)}")
    if not isinstance(payload, dict):
        raise AdapterError("payload 必须是对象")
    normalizer = _NORMALIZERS[kind]
    return [normalizer(item, request_id) for item in _extract_items(payload, kind)]


def items_for(records: Any, record_type: str) -> dict[str, Any]:
    """声明式页面用：返回指定类型记录的 payload 列表。"""
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    items = [
        item["payload"]
        for item in records
        if isinstance(item, dict)
        and item.get("recordType") == record_type
        and isinstance(item.get("payload"), dict)
    ]
    return {"items": items[:200], "count": len(items), "note": DISCLAIMER}


def summarize_records(records: Any) -> dict[str, Any]:
    """组件用：最近步数与序列（数据由调用方传入）。"""
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    series = []
    for item in records:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        if item.get("recordType") not in (None, "activity.session"):
            continue
        steps = payload.get("steps")
        if isinstance(steps, (int, float)) and not isinstance(steps, bool):
            series.append({"at": payload.get("capturedAt"), "value": int(steps)})
    series.sort(key=lambda point: str(point.get("at") or ""))
    latest = {"steps": series[-1]["value"], "at": series[-1]["at"]} if series else {}
    return {"latest": latest, "series": series[-30:], "note": DISCLAIMER}


def build_auth_url(client_id: Any, redirect_uri: Any, state: Any = "") -> str:
    if not isinstance(client_id, str) or not client_id.strip():
        raise AdapterError("clientId 缺失")
    if not isinstance(redirect_uri, str) or not redirect_uri.startswith(("https://", "http://")):
        raise AdapterError("redirectUri 必须是 http(s) 地址")
    query = {
        "response_type": "code",
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "scope": "activity sleep heartrate weight",
    }
    if isinstance(state, str) and state:
        query["state"] = state[:128]
    return f"{AUTH_URL}?{urlencode(query)}"

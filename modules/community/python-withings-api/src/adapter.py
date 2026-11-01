"""Withings 测量适配层：纯函数解析/映射，便于单测。

只依赖标准库；网络请求在 ``main.py`` 中懒加载 ``requests``。
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "withings"
MAX_GROUPS = 2000

AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
MEASURE_URL = "https://wbsapi.withings.net/measure"

# Withings measure type -> (payload 字段, 是否整数)
MEASURE_TYPES: dict[int, tuple[str, bool]] = {
    1: ("weightKg", False),
    4: ("heightM", False),
    5: ("fatFreeMassKg", False),
    6: ("fatRatioPct", False),
    8: ("fatMassKg", False),
    9: ("diastolicMmHg", True),
    10: ("systolicMmHg", True),
    11: ("heartRateBpm", True),
    12: ("temperatureC", False),
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _captured_at(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value <= 0:
            raise AdapterError("measure group date 必须是正数时间戳")
        return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and len(value) >= 10 and _DATE_RE.fullmatch(value[:10]):
        if "T" in value:
            return value
        return f"{value[:10]}T00:00:00Z"
    raise AdapterError("measure group 缺少合法 date")


def scale_measure(value: Any, unit: Any) -> float:
    """Withings 以 ``value × 10^unit`` 表示数值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("measure.value 必须是数字")
    if isinstance(unit, bool) or not isinstance(unit, int) or not -6 <= unit <= 6:
        raise AdapterError("measure.unit 必须是 -6..6 的整数")
    return round(float(value) * (10**unit), 3)


def normalize_measure_group(group: Any) -> dict[str, Any]:
    if not isinstance(group, dict):
        raise AdapterError("measure group 必须是对象")
    captured = _captured_at(group.get("date"))
    measures = group.get("measures")
    if not isinstance(measures, list) or not measures:
        raise AdapterError("measure group 缺少 measures")
    payload: dict[str, Any] = {"capturedAt": captured, "source": SOURCE}
    for measure in measures:
        if not isinstance(measure, dict):
            raise AdapterError("measure 条目必须是对象")
        raw_type = measure.get("type")
        if isinstance(raw_type, bool) or not isinstance(raw_type, int):
            raise AdapterError("measure.type 必须是整数")
        mapped = MEASURE_TYPES.get(raw_type)
        if mapped is None:
            continue
        field, is_int = mapped
        scaled = scale_measure(measure.get("value"), measure.get("unit"))
        if field == "fatRatioPct" and not 0 <= scaled <= 100:
            raise AdapterError("fatRatioPct 超出 0..100")
        payload[field] = int(scaled) if is_int else scaled
    if len(payload) == 2:
        raise AdapterError("measure group 缺少可识别的 Withings 指标")
    return {"recordType": "body.measurement", "payload": payload, "note": DISCLAIMER}


def records_from_export(payload: Any) -> list[dict[str, Any]]:
    """解析 ``getmeas`` 响应（``body.measuregrps``）或等价离线 JSON。"""
    if not isinstance(payload, dict):
        raise AdapterError("payload 必须是对象")
    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    groups = body.get("measuregrps", body.get("groups"))
    if not isinstance(groups, list):
        raise AdapterError("payload 缺少 measuregrps 数组")
    if len(groups) > MAX_GROUPS:
        raise AdapterError(f"单次最多导入 {MAX_GROUPS} 组测量")
    return [normalize_measure_group(group) for group in groups]


def summarize_records(records: Any) -> dict[str, Any]:
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    series: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        if item.get("recordType") not in (None, "body.measurement"):
            continue
        weight = payload.get("weightKg")
        if isinstance(weight, (int, float)) and not isinstance(weight, bool):
            series.append({"at": payload.get("capturedAt"), "value": float(weight)})
            latest = {"weightKg": float(weight), "at": payload.get("capturedAt")}
    series.sort(key=lambda point: str(point.get("at") or ""))
    return {"latest": latest, "series": series[-60:], "note": DISCLAIMER}


def items_for(records: Any) -> dict[str, Any]:
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    items = [
        item["payload"]
        for item in records
        if isinstance(item, dict)
        and item.get("recordType") == "body.measurement"
        and isinstance(item.get("payload"), dict)
    ]
    return {"items": items[:200], "count": len(items), "note": DISCLAIMER}


def build_auth_url(client_id: Any, redirect_uri: Any, state: Any = "") -> str:
    if not isinstance(client_id, str) or not client_id.strip():
        raise AdapterError("clientId 缺失")
    if not isinstance(redirect_uri, str) or not redirect_uri.startswith(("https://", "http://")):
        raise AdapterError("redirectUri 必须是 http(s) 地址")
    query = {
        "response_type": "code",
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "scope": "user.metrics",
    }
    if isinstance(state, str) and state:
        query["state"] = state[:128]
    return f"{AUTH_URL}?{urlencode(query)}"


def parse_token_response(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AdapterError("token 响应必须是对象")
    body = data.get("body") if isinstance(data.get("body"), dict) else data
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        reason = body.get("error") or data.get("status")
        raise AdapterError(f"token 响应缺少 access_token（{str(reason)[:80]}）", "UPSTREAM_ERROR")
    expires = body.get("expires_in")
    return {
        "accessToken": token,
        "refreshToken": body.get("refresh_token"),
        "expiresIn": int(expires) if isinstance(expires, (int, float)) else None,
        "userId": body.get("userid"),
        "scope": body.get("scope"),
        "note": DISCLAIMER,
    }


def parse_date_argument(value: Any, field: str = "date") -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise AdapterError(f"{field} 必须是 YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise AdapterError(f"{field} 不是合法日期") from exc
    return value

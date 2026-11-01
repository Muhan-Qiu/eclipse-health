"""Open-Meteo 天气（免费、无 key）。

- 先地理编码城市，再取未来 3 天日预报；
- 30 分钟进程内缓存，失败返回 ``None``，绝不把异常抛给教练回答；
- 只缓存成功结果，网络恢复后下一次请求会立即重试；
- 不记录城市名或响应体到日志（位置信息按隐私数据处理）。
"""

from __future__ import annotations

import copy
import math
import time
from datetime import UTC, datetime
from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 30 * 60
REQUEST_TIMEOUT_S = 6.0
MAX_CITY_LEN = 80
FORECAST_DAYS = 3

# city -> (expires_at, payload)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_weather_cache() -> None:
    _cache.clear()


def normalize_city(city: str | None) -> str:
    if not isinstance(city, str):
        return ""
    # 城市名会进入 URL 与缓存键；限制长度，避免明显的滥用输入。
    return " ".join(city.strip().split())[:MAX_CITY_LEN]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> int | None:
    parsed = _number(value)
    return round(parsed) if parsed is not None else None


def _at(series: Any, index: int) -> Any:
    return series[index] if isinstance(series, list) and index < len(series) else None


def _daily_days(daily: Any) -> list[dict[str, Any]]:
    if not isinstance(daily, dict):
        return []
    dates = daily.get("time")
    if not isinstance(dates, list):
        return []
    maxima = daily.get("temperature_2m_max")
    minima = daily.get("temperature_2m_min")
    precip = daily.get("precipitation_probability_max")
    codes = daily.get("weathercode")
    days: list[dict[str, Any]] = []
    for index, raw_date in enumerate(dates[:FORECAST_DAYS]):
        days.append(
            {
                "date": str(raw_date),
                "tempMax": _number(_at(maxima, index)),
                "tempMin": _number(_at(minima, index)),
                "precipitationProbability": _int(_at(precip, index)),
                "weatherCode": _int(_at(codes, index)),
            }
        )
    return days


async def _fetch_weather(
    city: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, transport=transport) as client:
        geocoding = await client.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        if geocoding.status_code >= 400:
            return None
        try:
            geo_payload = geocoding.json()
        except ValueError:
            return None
        results = geo_payload.get("results") if isinstance(geo_payload, dict) else None
        if not isinstance(results, list) or not results:
            return None
        place = results[0] if isinstance(results[0], dict) else {}
        latitude = _number(place.get("latitude"))
        longitude = _number(place.get("longitude"))
        if latitude is None or longitude is None:
            return None

        forecast = await client.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,weathercode"
                ),
                "timezone": "auto",
                "forecast_days": FORECAST_DAYS,
            },
        )
        if forecast.status_code >= 400:
            return None
        try:
            forecast_payload = forecast.json()
        except ValueError:
            return None
    if not isinstance(forecast_payload, dict):
        return None

    display_name = place.get("name")
    return {
        "city": str(display_name or city)[:MAX_CITY_LEN],
        "country": place.get("country") or None,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": forecast_payload.get("timezone") or None,
        "days": _daily_days(forecast_payload.get("daily")),
        "source": "open-meteo",
        "fetchedAt": datetime.now(UTC).isoformat(),
    }


async def get_weather(
    city: str | None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """城市为空、地理编码无结果或网络失败时返回 ``None``。"""
    key = normalize_city(city)
    if not key:
        return None

    moment = time.monotonic() if now is None else now
    cached = _cache.get(key)
    if cached is not None and moment < cached[0]:
        return copy.deepcopy(cached[1])

    try:
        weather = await _fetch_weather(key, transport=transport)
    except Exception:  # noqa: BLE001 - 天气失败不能影响教练主流程
        weather = None
    if weather is None:
        return None

    _cache[key] = (moment + CACHE_TTL_S, copy.deepcopy(weather))
    return weather


__all__ = [
    "CACHE_TTL_S",
    "clear_weather_cache",
    "get_weather",
    "normalize_city",
]

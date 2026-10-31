"""Open-Meteo 解析、缓存与失败降级。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from eclipse_health_backend.coach.weather import (
    CACHE_TTL_S,
    clear_weather_cache,
    get_weather,
    normalize_city,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_weather_cache()
    yield
    clear_weather_cache()


def _ok_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "上海",
                            "latitude": 31.23,
                            "longitude": 121.47,
                            "country": "中国",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Shanghai",
                "daily": {
                    "time": ["2026-10-31", "2026-11-01", "2026-11-02"],
                    "temperature_2m_max": [22.4, 20.1, 18.0],
                    "temperature_2m_min": [14.2, 13.0, 12.5],
                    "precipitation_probability_max": [10, 40, 80],
                    "weathercode": [1, 61, 95],
                },
            },
        )

    return httpx.MockTransport(handler)


def test_parse_forecast() -> None:
    weather = asyncio.run(get_weather("上海", transport=_ok_transport()))
    assert weather is not None
    assert weather["city"] == "上海"
    assert weather["source"] == "open-meteo"
    assert len(weather["days"]) == 3
    first = weather["days"][0]
    assert first["date"] == "2026-10-31"
    assert first["tempMax"] == 22.4
    assert first["tempMin"] == 14.2
    assert first["precipitationProbability"] == 10
    assert first["weatherCode"] == 1


def test_cache_hit_does_not_fetch_again() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _ok_transport().handle_request(request)

    transport = httpx.MockTransport(handler)
    assert asyncio.run(get_weather("上海", transport=transport, now=0)) is not None
    assert calls == 2  # geocoding + forecast
    assert asyncio.run(get_weather("上海", transport=transport, now=10)) is not None
    assert calls == 2


def test_cache_expires_after_ttl() -> None:
    assert asyncio.run(get_weather("上海", transport=_ok_transport(), now=0)) is not None

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    expired = asyncio.run(
        get_weather("上海", transport=httpx.MockTransport(failing), now=CACHE_TTL_S + 1)
    )
    assert expired is None


def test_http_error_returns_none() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    assert asyncio.run(get_weather("上海", transport=transport)) is None


def test_network_error_returns_none() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    assert asyncio.run(get_weather("上海", transport=httpx.MockTransport(failing))) is None


def test_no_results_returns_none() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    )
    assert asyncio.run(get_weather("不存在的城市", transport=transport)) is None


def test_blank_city_skips_network() -> None:
    def should_not_run(_request: httpx.Request) -> Any:
        raise AssertionError("network must not be used for blank city")

    transport = httpx.MockTransport(should_not_run)
    assert asyncio.run(get_weather(None, transport=transport)) is None
    assert asyncio.run(get_weather("   ", transport=transport)) is None
    assert normalize_city("  上海  ") == "上海"

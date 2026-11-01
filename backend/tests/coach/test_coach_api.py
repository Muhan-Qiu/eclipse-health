"""教练只读 API：路由可直接 include，不依赖 api/__init__.py。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eclipse_health_backend.coach import api as coach_api
from eclipse_health_backend.coach import context as coach_context


@pytest.fixture()
def coach_client(client: TestClient) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(coach_api.router, prefix="/api/v1")
    with TestClient(app) as test_client:
        yield test_client


def test_context_without_data(
    coach_client: TestClient, default_member: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_weather(_city: str | None) -> None:
        return None

    monkeypatch.setattr(coach_api, "get_weather", no_weather)
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)

    response = coach_client.get("/api/v1/coach/context")
    assert response.status_code == 200
    body = response.json()
    assert body["memberId"] == default_member["id"]
    assert body["health"] == {}
    assert body["exercises"] == []
    assert body["memory"] is None
    assert body["weather"] is None
    assert body["scores"] is None or body["scores"]["overall"] is None


def test_context_includes_weather(
    coach_client: TestClient, default_member: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    weather: dict[str, Any] = {
        "city": "上海",
        "days": [{"date": "2026-10-31", "tempMin": 14, "tempMax": 22}],
    }

    async def fake_weather(_city: str | None) -> dict[str, Any]:
        return weather

    monkeypatch.setattr(coach_api, "get_weather", fake_weather)
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)

    response = coach_client.get("/api/v1/coach/context", params={"city": "上海"})
    assert response.status_code == 200
    assert response.json()["weather"] == weather


def test_weather_endpoint_shape(
    coach_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_weather(_city: str | None) -> dict[str, Any]:
        return {"city": "上海", "days": []}

    monkeypatch.setattr(coach_api, "get_weather", fake_weather)
    response = coach_client.get("/api/v1/coach/weather", params={"city": " 上海 "})
    assert response.status_code == 200
    body = response.json()
    assert body == {"city": "上海", "available": True, "weather": {"city": "上海", "days": []}}


def test_weather_unavailable_is_not_an_error(
    coach_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_weather(_city: str | None) -> None:
        return None

    monkeypatch.setattr(coach_api, "get_weather", no_weather)
    response = coach_client.get("/api/v1/coach/weather")
    assert response.status_code == 200
    assert response.json() == {"city": "", "available": False, "weather": None}

"""OHS 路由：设置读写、连接测试、同步响应与未配置拒绝。"""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient
from ohs_helpers import requires_dpapi

from eclipse_health_backend.ohs import api
from eclipse_health_backend.ohs.client import OhsClient
from eclipse_health_backend.ohs.sync import SyncResult

pytestmark = requires_dpapi

API = "/api/v1/ohs"


def test_settings_start_unconfigured(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/settings")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is False
    assert body["hasToken"] is False
    assert body["baseUrl"] == "http://127.0.0.1:8080"


def test_save_settings_requires_token_on_first_save(api_client: TestClient) -> None:
    response = api_client.put(
        f"{API}/settings",
        json={"baseUrl": "http://127.0.0.1:8080", "userId": "u1"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ohs_token_required"


def test_save_and_read_settings_never_returns_token(api_client: TestClient) -> None:
    response = api_client.put(
        f"{API}/settings",
        json={
            "baseUrl": "http://127.0.0.1:8080/",
            "token": "tenant-secret",
            "userId": "u1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["baseUrl"] == "http://127.0.0.1:8080"
    assert body["userId"] == "u1"
    assert "token" not in body

    read = api_client.get(f"{API}/settings").json()
    assert read["configured"] is True
    assert "tenant-secret" not in json.dumps(read)


def test_connection_success(api_client: TestClient, monkeypatch) -> None:
    api_client.put(
        f"{API}/settings",
        json={"baseUrl": "http://127.0.0.1:8080", "token": "tenant-secret", "userId": "u1"},
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = {"users": [{"id": "u1", "name": "A"}]}
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(
        api,
        "build_client",
        lambda base, token: OhsClient(base, token, transport=httpx.MockTransport(handler)),
    )
    response = api_client.post(f"{API}/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["userCount"] == 1


def test_connection_401(api_client: TestClient, monkeypatch) -> None:
    api_client.put(
        f"{API}/settings",
        json={"baseUrl": "http://127.0.0.1:8080", "token": "bad-token"},
    )
    monkeypatch.setattr(
        api,
        "build_client",
        lambda base, token: OhsClient(
            base, token, transport=httpx.MockTransport(lambda _request: httpx.Response(401))
        ),
    )
    response = api_client.post(f"{API}/test")
    assert response.status_code == 401
    assert response.json()["code"] == "ohs_auth_failed"


def test_sync_route_returns_counts(api_client: TestClient, monkeypatch) -> None:
    def fake_sync(session, member_id, *, days=30):
        assert days == 7
        return SyncResult(
            created=2,
            skipped=1,
            failed=0,
            warnings=[{"code": "ohs_no_daily_data", "message": "none"}],
            user_id="u1",
            days=days,
        )

    monkeypatch.setattr(api, "sync_recent", fake_sync)
    response = api_client.post(f"{API}/sync", json={"days": 7})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "created": 2,
        "skipped": 1,
        "failed": 0,
        "warnings": [{"code": "ohs_no_daily_data", "message": "none"}],
        "userId": "u1",
        "days": 7,
    }


def test_sync_without_configuration_returns_422(api_client: TestClient) -> None:
    response = api_client.post(f"{API}/sync", json={"days": 30})
    assert response.status_code == 422
    assert response.json()["code"] == "ohs_not_configured"

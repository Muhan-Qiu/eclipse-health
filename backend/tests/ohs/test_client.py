"""OHS 客户端：URL 校验、认证状态、接口解析与网络失败。"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from eclipse_health_backend.domain.errors import InvalidInputError
from eclipse_health_backend.ohs.client import (
    DEFAULT_BASE_URL,
    OhsAuthError,
    OhsClient,
    OhsPermissionError,
    OhsUnreachableError,
    extract_daily_entries,
    extract_users,
    normalize_base_url,
)


def _client(handler: object, *, base_url: str = "http://127.0.0.1:8080") -> OhsClient:
    return OhsClient(base_url, "secret-token", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _json(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(payload).encode("utf-8"))


def test_normalize_base_url_defaults_and_strips_slash() -> None:
    assert normalize_base_url("") == DEFAULT_BASE_URL
    assert normalize_base_url("http://localhost:8080/") == "http://localhost:8080"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://127.0.0.1:8080",
        "http://user:pass@127.0.0.1:8080",
        "http://127.0.0.1:8080/?x=1",
        "http://127.0.0.1:8080/#frag",
        "http://",
    ],
)
def test_invalid_base_url_rejected(value: str) -> None:
    with pytest.raises(InvalidInputError) as excinfo:
        normalize_base_url(value)
    assert excinfo.value.code == "ohs_invalid_base_url"


def test_empty_token_rejected() -> None:
    with pytest.raises(InvalidInputError) as excinfo:
        OhsClient("http://127.0.0.1:8080", "   ")
    assert excinfo.value.code == "ohs_token_required"


def test_test_connection_tenant_and_user_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.url.path == "/v1/users"
        return _json({"users": [{"id": "u1", "name": "A"}, {"id": "u2"}]})

    with _client(handler) as client:
        info = client.test_connection()
    assert info["ok"] is True
    assert info["authType"] == "tenant"
    assert info["userCount"] == 2
    assert info["users"][0] == {"id": "u1", "name": "A"}


def test_test_connection_401() -> None:
    client = _client(lambda _request: _json({"error": "bad token"}, 401))
    with pytest.raises(OhsAuthError) as excinfo:
        client.test_connection()
    client.close()
    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "ohs_auth_failed"


def test_test_connection_403_means_limited_user_token() -> None:
    with _client(lambda _request: _json({}, 403)) as client:
        info = client.test_connection()
    assert info["ok"] is True
    assert info["authType"] == "user"
    assert info["warnings"][0]["code"] == "ohs_user_token_limited"


def test_list_users_403_raises_permission_error() -> None:
    with _client(lambda _request: _json({}, 403)) as client, pytest.raises(OhsPermissionError):
        client.list_users()


def test_network_error_maps_to_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with _client(handler) as client, pytest.raises(OhsUnreachableError) as excinfo:
        client.test_connection()
    assert excinfo.value.code == "ohs_unreachable"
    assert excinfo.value.status_code == 502


def test_fetch_daily_passes_range_and_parses_wrappers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.raw_path.decode().split("?", 1)[0]
        seen["from"] = request.url.params["from"]
        seen["to"] = request.url.params["to"]
        return _json({"data": {"days": [{"date": "2026-10-30", "steps": 1200}]}})

    with _client(handler) as client:
        entries = client.fetch_daily("u 1", _date("2026-10-01"), _date("2026-10-30"))
    assert seen == {
        "path": "/v1/users/u%201/daily",
        "from": "2026-10-01",
        "to": "2026-10-30",
    }
    assert entries == [{"date": "2026-10-30", "steps": 1200}]


def _date(value: str) -> date:
    return date.fromisoformat(value)


def test_extractors_tolerate_unexpected_shapes() -> None:
    assert extract_users({"data": {"items": [{"userId": 7}]}}) == [{"id": "7", "name": ""}]
    assert extract_users("nope") == []
    assert extract_daily_entries({"summary": {"date": "2026-10-30", "steps": 1}}) == [
        {"date": "2026-10-30", "steps": 1}
    ]
    assert extract_daily_entries({"unexpected": []}) == []

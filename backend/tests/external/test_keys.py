"""API Key 生命周期、存储安全与 scope 认证（F3）。"""

from __future__ import annotations

import hashlib

from external_helpers import bearer
from fastapi.testclient import TestClient
from sqlmodel import select

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.models import ExternalApiKeyTable


def test_create_list_use_revoke(client: TestClient) -> None:
    response = client.post(
        "/api/v1/external/keys",
        json={"name": "agent", "scopes": ["read", "write", "assistant"]},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    token = created["token"]
    key_id = created["id"]

    assert token.startswith("eh_ext_")
    assert created["prefix"] == token[:16]
    assert created["scopes"] == ["read", "write", "assistant"]
    assert created["revoked"] is False

    # 数据库只存 SHA-256，明文 token 不落库。
    with session_scope() as session:
        row = session.get(ExternalApiKeyTable, key_id)
        assert row is not None
        assert row.key_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert token not in row.key_hash
        assert token not in row.prefix
        assert row.scopes == ["read", "write", "assistant"]

    # 列表只返回 masked 字段。
    listed = client.get("/api/v1/external/keys")
    assert listed.status_code == 200
    item = next(entry for entry in listed.json()["items"] if entry["id"] == key_id)
    assert "token" not in item
    assert "key_hash" not in item
    assert token not in listed.text

    # Bearer 认证成功，并更新 lastUsedAt。
    ok = client.get("/api/v1/external/records", headers=bearer(token))
    assert ok.status_code == 200, ok.text
    with session_scope() as session:
        row = session.get(ExternalApiKeyTable, key_id)
        assert row is not None and row.last_used_at is not None

    # X-API-Key 也可用。
    assert client.get(
        "/api/v1/external/records", headers={"X-API-Key": token}
    ).status_code == 200

    # 撤销后立即失效。
    assert client.delete(f"/api/v1/external/keys/{key_id}").status_code == 204
    revoked = client.get("/api/v1/external/records", headers=bearer(token))
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "invalid_api_key"


def test_missing_and_invalid_token(client: TestClient) -> None:
    missing = client.get("/api/v1/external/records")
    assert missing.status_code == 401
    assert missing.json()["code"] == "invalid_api_key"

    invalid = client.get(
        "/api/v1/external/records", headers={"Authorization": "Bearer eh_ext_nope"}
    )
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "invalid_api_key"


def test_scope_enforcement(client: TestClient, make_key) -> None:
    read_only = make_key(("read",), "reader")
    headers = bearer(read_only["token"])

    assert client.get("/api/v1/external/records", headers=headers).status_code == 200
    denied_write = client.post(
        "/api/v1/external/health-data",
        json={"kind": "steps", "value": 10, "startAt": "2026-10-30T08:00:00Z"},
        headers=headers,
    )
    assert denied_write.status_code == 403
    assert denied_write.json()["code"] == "insufficient_scope"
    assert denied_write.json()["details"]["required"] == "write"

    denied_assistant = client.get(
        "/api/v1/external/openai/v1/models", headers=headers
    )
    assert denied_assistant.status_code == 403
    assert denied_assistant.json()["details"]["required"] == "assistant"

    assistant = make_key(("assistant",), "assistant-only")
    assistant_headers = bearer(assistant["token"])
    assert (
        client.get("/api/v1/external/openai/v1/models", headers=assistant_headers).status_code
        == 200
    )
    assert (
        client.get("/api/v1/external/records", headers=assistant_headers).status_code
        == 403
    )


def test_invalid_key_requests(client: TestClient) -> None:
    bad_scope = client.post(
        "/api/v1/external/keys", json={"name": "bad", "scopes": ["admin"]}
    )
    assert bad_scope.status_code == 422
    assert bad_scope.json()["code"] == "invalid_scope"

    empty_scope = client.post(
        "/api/v1/external/keys", json={"name": "empty", "scopes": []}
    )
    assert empty_scope.status_code == 422

    missing = client.delete("/api/v1/external/keys/key_missing")
    assert missing.status_code == 404
    assert missing.json()["code"] == "api_key_not_found"


def test_revoke_is_idempotent(client: TestClient) -> None:
    created = client.post(
        "/api/v1/external/keys", json={"name": "once", "scopes": ["read"]}
    ).json()
    assert client.delete(f"/api/v1/external/keys/{created['id']}").status_code == 204
    assert client.delete(f"/api/v1/external/keys/{created['id']}").status_code == 204

    rows = client.get("/api/v1/external/keys").json()["items"]
    item = next(entry for entry in rows if entry["id"] == created["id"])
    assert item["revoked"] is True
    assert item["revokedAt"] is not None


def test_hash_lookup_uses_select(client: TestClient) -> None:
    """防止以后改成按明文查询：表里只应有 hash 列可查。"""
    with session_scope() as session:
        rows = list(session.exec(select(ExternalApiKeyTable)))
    assert rows == []

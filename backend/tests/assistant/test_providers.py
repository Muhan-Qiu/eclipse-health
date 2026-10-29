"""Provider 配置与 DPAPI 凭据（H3）。

覆盖：加密往返、API 脱敏、磁盘无明文、日志无 key、非法输入。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from llm_test_support import SECRET

from eclipse_health_backend.llm.providers import (
    SecretError,
    decrypt_secret,
    encrypt_secret,
    get_provider_store,
)


def test_dpapi_roundtrip() -> None:
    token = encrypt_secret(SECRET)
    assert token.startswith("dpapi:v1:")
    assert SECRET not in token
    assert decrypt_secret(token) == SECRET


def test_dpapi_rejects_bad_payload() -> None:
    with pytest.raises(SecretError):
        decrypt_secret("dpapi:v1:not-base64!!")
    with pytest.raises(SecretError):
        decrypt_secret("plain-text")


def test_provider_crud_never_returns_key(
    client: TestClient, providers_file: Path
) -> None:
    created = client.put(
        "/api/v1/assistant/providers/llm_openai_1",
        json={
            "kind": "openai",
            "label": "OpenAI",
            "model": "gpt-4.1-mini",
            "baseUrl": "https://api.openai.com/v1/",
            "apiKey": SECRET,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["configured"] is True
    assert body["baseUrl"] == "https://api.openai.com/v1"
    assert SECRET not in json.dumps(body)

    listed = client.get("/api/v1/assistant/providers")
    assert listed.status_code == 200
    assert SECRET not in listed.text
    assert listed.json()["items"][0]["configured"] is True

    # 磁盘上只有 DPAPI 密文
    stored = providers_file.read_text(encoding="utf-8")
    assert SECRET not in stored
    assert "dpapi:v1:" in stored
    key_ref = json.loads(stored)["providers"][0]["keyRef"]
    assert decrypt_secret(key_ref) == SECRET

    # 不带 apiKey 的更新保留原 key
    updated = client.put(
        "/api/v1/assistant/providers/llm_openai_1", json={"label": "OpenAI 2"}
    ).json()
    assert updated["configured"] is True
    assert updated["label"] == "OpenAI 2"

    # 显式清空
    cleared = client.put(
        "/api/v1/assistant/providers/llm_openai_1", json={"clearKey": True}
    ).json()
    assert cleared["configured"] is False

    assert client.delete("/api/v1/assistant/providers/llm_openai_1").status_code == 204
    assert client.delete("/api/v1/assistant/providers/llm_openai_1").status_code == 404


def test_provider_validation(client: TestClient, providers_file: Path) -> None:
    bad_kind = client.put(
        "/api/v1/assistant/providers/llm_bad", json={"kind": "evil", "model": "x"}
    )
    assert bad_kind.status_code == 422

    bad_url = client.put(
        "/api/v1/assistant/providers/llm_bad",
        json={"kind": "ollama", "baseUrl": "file:///etc/passwd", "model": "x"},
    )
    assert bad_url.status_code == 422
    assert bad_url.json()["code"] == "invalid_base_url"

    credential_url = client.put(
        "/api/v1/assistant/providers/llm_bad",
        json={
            "kind": "openai",
            "baseUrl": "https://user:supersecret@example.com/v1",
            "model": "x",
        },
    )
    assert credential_url.status_code == 422
    assert "supersecret" not in credential_url.text

    missing = client.post("/api/v1/assistant/providers/llm_missing/test")
    assert missing.status_code == 404

    disabled = client.put(
        "/api/v1/assistant/providers/llm_off",
        json={"kind": "mock", "model": "mock-1", "enabled": False},
    )
    assert disabled.status_code == 200
    test_disabled = client.post("/api/v1/assistant/providers/llm_off/test")
    assert test_disabled.status_code == 409


def test_key_never_appears_in_logs(
    client: TestClient, providers_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="eclipse_health_backend"):
        client.put(
            "/api/v1/assistant/providers/llm_openai_2",
            json={"kind": "openai", "model": "gpt-4.1-mini", "apiKey": SECRET},
        )
        client.get("/api/v1/assistant/providers")
        provider = get_provider_store().get("llm_openai_2")
        assert get_provider_store().resolve_api_key(provider) == SECRET
    assert SECRET not in caplog.text


def test_mock_provider_test_endpoint(client: TestClient, mock_provider: dict) -> None:
    response = client.post(f"/api/v1/assistant/providers/{mock_provider['id']}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert SECRET not in json.dumps(body)

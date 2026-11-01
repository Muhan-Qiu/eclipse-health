"""A7 服务商预设：前缀映射、旧数据迁移、校验与脱敏。

覆盖：

- 预设列表覆盖要求中的全部服务商，且不含任何 Key；
- 每个预设的 ``litellmProvider`` 都能被当前 LiteLLM 解析成同一前缀；
- 模型字符串按 ``<litellmProvider>/<model>`` 生成；
- 旧 providers.json（无 presetId / litellmProvider / needsKey）仍能加载并保存；
- 未知预设、缺少必填 base URL、非法前缀返回结构化错误；
- 测试连接的报错不含 Key。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from llm_test_support import SECRET

from eclipse_health_backend.llm.provider_presets import PRESETS, get_preset
from eclipse_health_backend.llm.providers import Provider

REQUIRED_PRESETS = {
    "openai",
    "anthropic",
    "gemini",
    "azure-openai",
    "bedrock",
    "vertex-ai",
    "deepseek",
    "moonshot",
    "zhipu",
    "dashscope",
    "minimax",
    "baichuan",
    "stepfun",
    "yi",
    "volcengine",
    "hunyuan",
    "siliconflow",
    "openrouter",
    "groq",
    "together",
    "fireworks",
    "mistral",
    "xai",
    "perplexity",
    "cerebras",
    "sambanova",
    "novita",
    "nebius",
    "ollama",
    "lm-studio",
    "vllm",
    "oneapi",
    "cc-switch",
}


def _legacy_record(provider_id: str, kind: str, model: str) -> dict:
    return {
        "id": provider_id,
        "kind": kind,
        "label": kind,
        "model": model,
        "baseUrl": _legacy_base_url(kind),
        "enabled": True,
        "keyRef": None,
        "options": {},
        "createdAt": "2026-10-01T00:00:00+00:00",
        "updatedAt": "2026-10-01T00:00:00+00:00",
    }


def _legacy_base_url(kind: str) -> str | None:
    return {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com",
        "ollama": "http://127.0.0.1:11434",
        "mock": None,
    }[kind]


def test_presets_cover_required_providers(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/provider-presets")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert REQUIRED_PRESETS <= ids
    assert {item.id for item in PRESETS} == ids
    assert len(ids) == len(items), "preset ids must be unique"
    assert SECRET not in response.text
    for item in items:
        assert item["kind"] in {"openai", "anthropic", "ollama", "mock"}
        assert item["group"] in {"official", "china", "gateway", "local", "custom", "demo"}
        assert not item["requiresBaseUrl"] or item["baseUrl"] is None


@pytest.mark.parametrize(
    "preset",
    [item for item in PRESETS if item.litellm_provider],
    ids=[item.id for item in PRESETS if item.litellm_provider],
)
def test_preset_prefix_resolves_in_litellm(preset) -> None:
    from litellm.utils import get_llm_provider

    _, provider, _, _ = get_llm_provider(f"{preset.litellm_provider}/{preset.default_model}")
    assert provider == preset.litellm_provider


def test_litellm_model_string_and_inferred_fields() -> None:
    deepseek = Provider(
        id="llm_ds",
        kind="openai",
        label="DeepSeek",
        model="deepseek-chat",
        preset_id="deepseek",
        litellm_provider="deepseek",
        needs_key_value=True,
    )
    assert deepseek.litellm_model == "deepseek/deepseek-chat"
    assert deepseek.error_kind == "deepseek"
    assert deepseek.needs_key is True
    assert deepseek.is_local is False

    # 旧记录没有 litellmProvider：回退到 kind，行为和改造前一致。
    legacy = Provider(id="llm_old", kind="openai", label="OpenAI", model="gpt-4.1-mini")
    assert legacy.litellm_model == "openai/gpt-4.1-mini"
    assert legacy.needs_key is True
    assert legacy.is_local is False

    local = Provider(
        id="llm_local",
        kind="openai",
        label="LM Studio",
        model="local-model",
        litellm_provider="openai",
        needs_key_value=False,
        local_value=True,
    )
    assert local.needs_key is False
    assert local.is_local is True


def test_legacy_provider_records_still_load(
    client: TestClient, providers_file: Path
) -> None:
    providers_file.parent.mkdir(parents=True, exist_ok=True)
    providers_file.write_text(
        json.dumps(
            {
                "version": 1,
                "providers": [
                    _legacy_record("llm_old_openai", "openai", "gpt-4.1-mini"),
                    _legacy_record("llm_old_ollama", "ollama", "llama3.1"),
                ],
            }
        ),
        encoding="utf-8",
    )

    items = {
        item["id"]: item
        for item in client.get("/api/v1/assistant/providers").json()["items"]
    }
    old_openai = items["llm_old_openai"]
    assert old_openai["presetId"] is None
    assert old_openai["litellmProvider"] == "openai"
    assert old_openai["needsKey"] is True
    assert old_openai["isLocal"] is False

    old_ollama = items["llm_old_ollama"]
    assert old_ollama["litellmProvider"] is None
    assert old_ollama["needsKey"] is False
    assert old_ollama["isLocal"] is True

    # 旧客户端不带 presetId 的更新仍然照常工作。
    updated = client.put(
        "/api/v1/assistant/providers/llm_old_openai", json={"model": "gpt-4.1"}
    ).json()
    assert updated["litellmProvider"] == "openai"
    assert updated["needsKey"] is True
    assert updated["model"] == "gpt-4.1"


def test_save_preset_derives_fields_and_keeps_key_secret(
    client: TestClient, providers_file: Path
) -> None:
    response = client.put(
        "/api/v1/assistant/providers/llm_preset_deepseek",
        json={"presetId": "deepseek", "apiKey": SECRET},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["presetId"] == "deepseek"
    assert body["kind"] == "openai"
    assert body["litellmProvider"] == "deepseek"
    assert body["needsKey"] is True
    assert body["isLocal"] is False
    assert body["baseUrl"] == "https://api.deepseek.com/v1"
    assert body["label"] == "DeepSeek"
    assert body["model"] == "deepseek-chat"
    assert body["configured"] is True
    assert SECRET not in response.text

    stored = providers_file.read_text(encoding="utf-8")
    assert SECRET not in stored
    assert "dpapi:v1:" in stored
    record = json.loads(stored)["providers"][0]
    assert record["presetId"] == "deepseek"
    assert record["litellmProvider"] == "deepseek"
    assert record["needsKey"] is True


def test_local_and_keyless_presets(client: TestClient, providers_file: Path) -> None:
    body = client.put(
        "/api/v1/assistant/providers/llm_lmstudio", json={"presetId": "lm-studio"}
    ).json()
    assert body["needsKey"] is False
    assert body["isLocal"] is True
    assert body["configured"] is False
    assert body["baseUrl"] == "http://127.0.0.1:1234/v1"

    ollama = client.put(
        "/api/v1/assistant/providers/llm_ollama", json={"presetId": "ollama"}
    ).json()
    assert ollama["kind"] == "ollama"
    assert ollama["litellmProvider"] is None
    assert ollama["needsKey"] is False
    assert ollama["isLocal"] is True


def test_unknown_preset_is_structured_error(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/providers/llm_unknown", json={"presetId": "not-a-preset"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_preset"


def test_preset_requires_base_url(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/providers/llm_custom", json={"presetId": "custom-openai"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "base_url_required"

    bad_url = client.put(
        "/api/v1/assistant/providers/llm_custom",
        json={"presetId": "custom-openai", "baseUrl": "file:///etc/passwd"},
    )
    assert bad_url.status_code == 422
    assert bad_url.json()["code"] == "invalid_base_url"

    saved = client.put(
        "/api/v1/assistant/providers/llm_custom",
        json={
            "presetId": "custom-openai",
            "baseUrl": "https://gateway.example.com/v1",
            "model": "house-model",
            "apiKey": SECRET,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["litellmProvider"] == "openai"
    assert saved.json()["baseUrl"] == "https://gateway.example.com/v1"


def test_invalid_litellm_provider_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/providers/llm_bad_prefix",
        json={"kind": "openai", "litellmProvider": "evil", "model": "x"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_litellm_provider"


def test_preset_kind_cannot_be_overridden(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/providers/llm_kind",
        json={"presetId": "deepseek", "kind": "anthropic", "model": "deepseek-chat"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_provider_kind"


def test_test_connection_requires_key(client: TestClient, providers_file: Path) -> None:
    client.put(
        "/api/v1/assistant/providers/llm_nokey", json={"presetId": "deepseek"}
    )
    response = client.post("/api/v1/assistant/providers/llm_nokey/test")
    assert response.status_code == 409
    assert response.json()["code"] == "missing_api_key"
    assert SECRET not in response.text


def test_test_connection_error_is_sanitized(
    client: TestClient, providers_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put(
        "/api/v1/assistant/providers/llm_probe",
        json={"presetId": "deepseek", "apiKey": SECRET},
    )

    class _AuthError(Exception):
        status_code = 401

    async def _fail(**_kwargs):
        raise _AuthError(f"invalid key {SECRET}")

    import litellm

    monkeypatch.setattr(litellm, "acompletion", _fail)

    response = client.post("/api/v1/assistant/providers/llm_probe/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert SECRET not in json.dumps(body)
    assert "authentication failed" in body["message"]
    assert "deepseek" in body["message"]


def test_preset_lookup_helper() -> None:
    assert get_preset("deepseek") is not None
    assert get_preset("custom-openai").requires_base_url is True
    assert get_preset("") is None
    assert get_preset("nope") is None

"""Provider 能力探测与错误映射（B4-08）。

覆盖：401/403/429/5xx/连接失败→可读错误；Ollama tags/show/chat 探测；
模型未安装、工具能力未知；mock 也能返回能力字段。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from eclipse_health_backend.api.assistant import _test_ollama
from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider


def _provider(model: str = "qwen3:4b", base_url: str = "http://127.0.0.1:11434") -> Provider:
    return Provider(
        id="llm_ollama_test",
        kind="ollama",
        label="Ollama",
        model=model,
        base_url=base_url,
    )


def test_http_status_mapping() -> None:
    cases = {
        401: ("openai_auth_error", "authentication failed"),
        403: ("openai_auth_error", "access denied"),
        404: ("openai_not_found", "not found"),
        429: ("openai_rate_limited", "rate limited"),
        503: ("openai_server_error", "server error"),
    }
    for status, (code, fragment) in cases.items():
        error = agent.sanitize_error("openai", RuntimeError("raw secret text"), status=status)
        assert error.code == code
        assert fragment in error.message
        assert "raw secret text" not in error.message
        assert f"HTTP {status}" in error.message


def test_connection_error_mapping() -> None:
    error = agent.sanitize_error("ollama", httpx.ConnectError("127.0.0.1 refused"))
    assert error.code == "ollama_network_error"
    assert "refused" not in error.message

    timeout = agent.sanitize_error("ollama", httpx.ReadTimeout("slow"))
    assert timeout.code == "timeout"
    assert "slow" not in timeout.message


def test_retryable_classification() -> None:
    assert agent.is_retryable(agent.LLMError("openai_rate_limited", "x"))
    assert agent.is_retryable(agent.LLMError("openai_server_error", "x"))
    assert agent.is_retryable(agent.LLMError("openai_network_error", "x"))
    assert not agent.is_retryable(agent.LLMError("openai_auth_error", "x"))
    assert not agent.is_retryable(agent.LLMError("timeout", "x"))
    assert not agent.is_retryable(None)


def test_usage_merge_sums_rounds() -> None:
    merged = agent.merge_usage(
        agent.make_usage(100, 20), agent.make_usage(180, 30)
    )
    assert merged == {
        "promptTokens": 280,
        "completionTokens": 50,
        "totalTokens": 330,
        "source": "provider",
    }

    estimated = agent.merge_usage(
        agent.make_usage(100, 20, source="estimate"), agent.make_usage(None, None)
    )
    assert estimated["source"] == "estimate"
    assert estimated["promptTokens"] == 100


def _ollama_transport(
    *,
    models: list[str],
    capabilities: list[str] | None,
    chat_status: int = 200,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": name} for name in models]}
            )
        if request.url.path == "/api/show":
            if capabilities is None:
                return httpx.Response(404, json={"error": "unknown"})
            return httpx.Response(200, json={"capabilities": capabilities})
        if request.url.path == "/api/chat":
            if chat_status >= 400:
                return httpx.Response(chat_status, json={"error": "nope"})
            return httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "pong"},
                    "prompt_eval_count": 12,
                    "eval_count": 2,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_ollama_probe_reports_capabilities() -> None:
    transport = _ollama_transport(
        models=["qwen3:4b", "qwen3.5:9b"], capabilities=["completion", "tools"]
    )
    probe = asyncio.run(_test_ollama(_provider(), transport=transport))
    assert probe.ok is True
    assert probe.available is True
    assert probe.supports_tools is True
    assert "qwen3:4b" in probe.models
    assert probe.latency_ms is not None


def test_ollama_probe_without_tool_capability() -> None:
    transport = _ollama_transport(models=["qwen2.5vl:7b"], capabilities=["completion"])
    probe = asyncio.run(_test_ollama(_provider("qwen2.5vl:7b"), transport=transport))
    assert probe.ok is True
    assert probe.supports_tools is False


def test_ollama_probe_show_missing_keeps_capability_unknown() -> None:
    transport = _ollama_transport(models=["qwen3:4b"], capabilities=None)
    probe = asyncio.run(_test_ollama(_provider(), transport=transport))
    assert probe.ok is True
    assert probe.supports_tools is None


def test_ollama_probe_missing_model() -> None:
    transport = _ollama_transport(models=["qwen3.5:9b"], capabilities=["tools"])
    probe = asyncio.run(_test_ollama(_provider("llama3.2:3b"), transport=transport))
    assert probe.ok is False
    assert probe.available is False
    assert "未安装" in probe.message
    assert "qwen3.5:9b" in probe.message


def test_ollama_probe_http_error_is_sanitized() -> None:
    transport = _ollama_transport(
        models=["qwen3:4b"], capabilities=["tools"], chat_status=500
    )
    with pytest.raises(agent.LLMError) as excinfo:
        asyncio.run(_test_ollama(_provider(), transport=transport))
    assert excinfo.value.code == "ollama_server_error"
    assert "HTTP 500" in excinfo.value.message


def test_ollama_probe_connection_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(agent.LLMError) as excinfo:
        asyncio.run(_test_ollama(_provider(), transport=httpx.MockTransport(handler)))
    assert excinfo.value.code == "ollama_network_error"
    assert "refused" not in excinfo.value.message


def test_ollama_probe_timeout_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["tools"]})
        raise httpx.ReadTimeout("cold start", request=request)

    with pytest.raises(agent.LLMError) as excinfo:
        asyncio.run(_test_ollama(_provider(), transport=httpx.MockTransport(handler)))
    assert excinfo.value.code == "timeout"
    assert "cold start" not in excinfo.value.message


def test_mock_test_endpoint_reports_tools(client: TestClient, mock_provider: dict) -> None:
    response = client.post(f"/api/v1/assistant/providers/{mock_provider['id']}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["available"] is True
    assert body["supportsTools"] is True
    assert "key" not in json.dumps(body).lower()

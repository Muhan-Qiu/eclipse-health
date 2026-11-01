"""LLM 错误分类与流式 usage 补口（C1）。

- LiteLLM 会把 ``httpx.ConnectError`` 包装成 ``InternalServerError(status=500)``；
  必须沿异常链识别为 ``*_network_error``，不能误报成 server error。
- Anthropic 流式 usage 可能落在最终 chunk、``message_delta`` 或隐藏字段里，
  能取到就补上，取不到保持 None，绝不伪造。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider


def _provider() -> Provider:
    return Provider(id="llm_test", kind="anthropic", label="Test", model="claude-test")


def test_connect_error_maps_to_network_error() -> None:
    error = agent.sanitize_error("anthropic", httpx.ConnectError("secret host"))
    assert error.code == "anthropic_network_error"
    assert error.message == "anthropic connection failed"
    assert "secret" not in error.message


def test_wrapped_connect_error_is_not_a_server_error() -> None:
    wrapped = RuntimeError("provider 500 wrapper")
    wrapped.__cause__ = httpx.ConnectError("connection refused")
    error = agent.sanitize_error("anthropic", wrapped, status=500)
    assert error.code == "anthropic_network_error"


def test_plain_500_stays_server_error() -> None:
    error = agent.sanitize_error("openai", RuntimeError("upstream"), status=500)
    assert error.code == "openai_server_error"
    assert error.message == "openai server error (HTTP 500)"


def test_timeout_is_still_timeout() -> None:
    error = agent.sanitize_error("ollama", httpx.ReadTimeout("slow"))
    assert error.code == "timeout"


def _chunk(**kwargs: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "usage": None,
        "choices": [],
        "model_extra": None,
        "_hidden_params": None,
        "provider_specific_fields": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _text_chunk(text: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=text, tool_calls=None)
    return _chunk(choices=[SimpleNamespace(delta=delta)])


def _collect(adapter: agent.ChatAdapter) -> list[dict[str, Any]]:
    async def runner() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async for event in adapter.stream(
            [{"role": "user", "content": "hi"}], None, asyncio.Event()
        ):
            events.append(event)
        return events

    return asyncio.run(runner())


def test_stream_merges_partial_usage_from_message_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    async def fake_acompletion(**_kwargs: Any) -> Any:
        async def chunks() -> Any:
            yield _text_chunk("hello")
            # message_start 只给输入 tokens
            yield _chunk(usage={"input_tokens": 11})
            # message_delta 只给输出 tokens（Anthropic 常见形状）
            yield _chunk(usage={"output_tokens": 7})

        return chunks()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    events = _collect(agent.LiteLLMAdapter(_provider(), "test-key"))

    usage = next(event["usage"] for event in events if event["type"] == "usage")
    assert usage == {
        "promptTokens": 11,
        "completionTokens": 7,
        "totalTokens": 18,
        "source": "provider",
    }


def test_stream_reads_usage_from_hidden_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    async def fake_acompletion(**_kwargs: Any) -> Any:
        async def chunks() -> Any:
            yield _text_chunk("hello")
            # LiteLLM 某些版本把 message_delta usage 放进 model_extra
            yield _chunk(model_extra={"usage": {"prompt_tokens": 5, "completion_tokens": 4}})

        return chunks()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    events = _collect(agent.LiteLLMAdapter(_provider(), "test-key"))

    usage = next(event["usage"] for event in events if event["type"] == "usage")
    assert usage["promptTokens"] == 5
    assert usage["completionTokens"] == 4
    assert usage["totalTokens"] == 9


def test_stream_without_usage_keeps_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    async def fake_acompletion(**_kwargs: Any) -> Any:
        async def chunks() -> Any:
            yield _text_chunk("hello")

        return chunks()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    events = _collect(agent.LiteLLMAdapter(_provider(), "test-key"))

    assert all(event["type"] != "usage" for event in events)

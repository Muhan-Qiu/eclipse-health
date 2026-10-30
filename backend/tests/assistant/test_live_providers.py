r"""真实外部 provider 联调（B5-74）：默认跳过。

启用方式（PowerShell）：

```powershell
$env:EH_TEST_LIVE_LLM="1"
$env:EH_TEST_ANTHROPIC_BASE_URL="http://127.0.0.1:15721"  # 可选，默认取 ANTHROPIC_BASE_URL
$env:EH_TEST_ANTHROPIC_API_KEY="..."                      # 可选，默认取 ANTHROPIC_AUTH_TOKEN
$env:EH_TEST_ANTHROPIC_MODEL="..."                        # 可选，默认取 ANTHROPIC_MODEL
backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant\test_live_providers.py -m slow -q
```

安全约定：只读取环境变量名对应的值，不打印、不落盘；断言失败信息里只出现
provider 类型、模型名与 HTTP 状态。缺凭据时 skip，不伪造结果。

本机实测结果见 ``reports/B5-llm-live-report.md``。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# LiteLLM 默认在导入时联网拉取模型价格表；本机/离线环境会拖慢首轮 60 s。
# 测试里固定用本地表，避免把网络耗时算进首 token 延迟。
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import pytest
from assistant_helpers import create_record, parse_sse, seed_analysis
from fastapi.testclient import TestClient

from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider

PROVIDER_ID = "llm_live_proxy"
NON_DIAGNOSTIC = "不构成医学诊断"


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


LIVE_ENABLED = os.environ.get("EH_TEST_LIVE_LLM") == "1"
BASE_URL = _first_env("EH_TEST_ANTHROPIC_BASE_URL", "ANTHROPIC_BASE_URL")
API_KEY = _first_env(
    "EH_TEST_ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"
)
MODEL = _first_env("EH_TEST_ANTHROPIC_MODEL", "ANTHROPIC_MODEL")


def live_provider() -> tuple[Provider, str]:
    """返回 (provider, api_key)；缺开关或凭据时 skip，绝不回退到假 key。"""
    if not LIVE_ENABLED:
        pytest.skip("set EH_TEST_LIVE_LLM=1 to run live provider tests")
    missing = [
        label
        for label, value in (
            ("EH_TEST_ANTHROPIC_BASE_URL|ANTHROPIC_BASE_URL", BASE_URL),
            ("EH_TEST_ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN", API_KEY),
            ("EH_TEST_ANTHROPIC_MODEL|ANTHROPIC_MODEL", MODEL),
        )
        if not value
    ]
    if missing:
        pytest.skip("缺凭据：" + ", ".join(missing))
    provider = Provider(
        id=PROVIDER_ID,
        kind="anthropic",
        label="Live Anthropic-compatible proxy",
        model=MODEL or "",
        base_url=BASE_URL,
    )
    return provider, API_KEY or ""


def save_provider(client: TestClient) -> Provider:
    provider, api_key = live_provider()
    response = client.put(
        f"/api/v1/assistant/providers/{provider.id}",
        json={
            "kind": provider.kind,
            "label": provider.label,
            "model": provider.model,
            "baseUrl": provider.base_url,
            "apiKey": api_key,
        },
    )
    assert response.status_code == 200, response.text
    return provider


async def drain_stream(
    provider: Provider,
    api_key: str,
    prompt: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """直接消费 adapter：记录首 token 延迟、文本、工具调用与 usage。"""
    adapter = agent.adapter_for(provider, api_key)
    cancel = asyncio.Event()
    started = time.perf_counter()
    first_token_ms: int | None = None
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None

    async with asyncio.timeout(timeout_s):
        async for chunk in adapter.stream(
            [{"role": "user", "content": prompt}], tools, cancel
        ):
            kind = chunk.get("type")
            if kind == "token":
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - started) * 1000)
                text_parts.append(str(chunk.get("text") or ""))
            elif kind == "tool_calls":
                tool_calls.extend(chunk.get("calls") or [])
            elif kind == "usage":
                usage = chunk.get("usage")

    return {
        "text": "".join(text_parts),
        "firstTokenMs": first_token_ms,
        "totalMs": int((time.perf_counter() - started) * 1000),
        "toolCalls": tool_calls,
        "usage": usage,
    }


def expect_llm_error(provider: Provider, api_key: str) -> agent.LLMError:
    async def run() -> None:
        adapter = agent.adapter_for(provider, api_key)
        async for _chunk in adapter.stream(
            [{"role": "user", "content": "ping"}], None, asyncio.Event()
        ):
            pass

    with pytest.raises(agent.LLMError) as excinfo:
        asyncio.run(run())
    return excinfo.value


@pytest.mark.slow
def test_live_non_stream_usage_and_latency() -> None:
    """非流式一轮：provider 返回真实 usage 与延迟。"""
    provider, api_key = live_provider()
    litellm = pytest.importorskip("litellm")
    started = time.perf_counter()
    try:
        response = asyncio.run(
            litellm.acompletion(
                model=f"{provider.kind}/{provider.model}",
                messages=[{"role": "user", "content": "只回答两个字：正常"}],
                max_tokens=256,
                api_key=api_key,
                api_base=provider.base_url,
                timeout=90,
            )
        )
    except Exception as exc:  # noqa: BLE001 - 网络/凭据问题按 skip 处理，不伪造延迟
        pytest.skip(f"provider unavailable: {type(exc).__name__}")
    latency_ms = int((time.perf_counter() - started) * 1000)
    assert response.choices[0].message.content
    usage = response.usage
    assert usage is not None, "non-streaming response must include usage"
    assert usage.prompt_tokens and usage.completion_tokens
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
    assert latency_ms > 0


@pytest.mark.slow
def test_live_stream_first_token_and_usage() -> None:
    """流式一轮：首 token 时间、文本、usage（Anthropic 兼容流可能不带 usage）。"""
    provider, api_key = live_provider()
    result = asyncio.run(
        drain_stream(provider, api_key, "用一句话说明你是什么模型。")
    )
    assert result["text"].strip(), "streaming produced no text"
    assert result["firstTokenMs"] is not None
    assert result["firstTokenMs"] < 60_000
    # Anthropic Messages 流把 usage 放在 message_delta；当前 LiteLLM 版本会丢弃。
    # 有 usage 时必须来自 provider，不能是估算值。
    if result["usage"] is not None:
        assert result["usage"]["source"] == "provider"
        assert result["usage"]["totalTokens"]


@pytest.mark.slow
def test_live_stream_tool_call() -> None:
    """工具调用：直接给 adapter 一个 list_records 工具，模型应返回结构化调用。"""
    provider, api_key = live_provider()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_records",
                "description": "List the user's ECG records",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                    "required": [],
                },
            },
        }
    ]
    result = asyncio.run(
        drain_stream(
            provider,
            api_key,
            "请调用 list_records 工具列出我的记录，limit 设为 5。",
            tools=tools,
        )
    )
    calls = result["toolCalls"]
    assert calls, "model did not emit a tool call"
    assert calls[0]["name"] == "list_records"
    assert isinstance(calls[0]["args"], dict)


@pytest.mark.slow
def test_live_api_turn_completes_with_tool_and_citation(
    client: TestClient, providers_file, default_member: dict
) -> None:
    """真实一轮：SSE done、工具结果、引用、非诊断声明、落库 completed。"""
    provider = save_provider(client)
    record = create_record(client, default_member["id"])
    seed_analysis(record["id"])
    session = client.post(
        "/api/v1/assistant/sessions",
        json={"providerId": provider.id, "recordId": record["id"]},
    ).json()

    with client.stream(
        "POST",
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        json={
            "content": "请用 list_records 工具列出我的记录，并告诉我最近一条记录的记录 ID。",
            "providerId": provider.id,
            "recordId": record["id"],
        },
    ) as response:
        assert response.status_code == 200, response.text
        events = parse_sse(list(response.iter_lines()))

    names = [name for name, _ in events]
    assert "error" not in names, [data for name, data in events if name == "error"]
    tool_calls = [data for name, data in events if name == "tool_call"]
    assert tool_calls, "expected at least one tool call"
    known_tools = {
        str(item["function"]["name"]) for item in agent.TOOL_SPECS
    }
    assert tool_calls[0]["name"] in known_tools
    tool_results = [data for name, data in events if name == "tool_result"]
    assert tool_results and all(item["ok"] for item in tool_results)

    citations = [data for name, data in events if name == "citation"]
    assert any(item.get("id") == record["id"] for item in citations), citations

    done = [data for name, data in events if name == "done"]
    assert done, "missing done event"
    final = done[-1]
    assert final["content"].strip()
    assert NON_DIAGNOSTIC in final["content"]
    assert final["toolCalls"] >= 1
    assert final["durationMs"] > 0

    stored = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"]
    assistant = [item for item in stored if item["role"] == "assistant"][-1]
    assert assistant["status"] == "completed"
    assert assistant["transparency"]["provider"]["kind"] == "anthropic"


@pytest.mark.slow
def test_live_api_cancel_stops_stream(client: TestClient, providers_file) -> None:
    """流式中取消：状态落库 cancelled，SSE done 带 cancelled。"""
    provider = save_provider(client)
    session = client.post(
        "/api/v1/assistant/sessions", json={"providerId": provider.id}
    ).json()

    lines: list[str] = []
    errors: list[BaseException] = []

    def stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/v1/assistant/sessions/{session['id']}/messages",
                json={
                    "content": "请用医生风格详细分析我的记录，并逐条解释所有测量值。",
                    "providerId": provider.id,
                    "style": "doctor",
                },
            ) as response:
                lines.extend(response.iter_lines())
        except BaseException as exc:  # noqa: BLE001 - 线程内错误带回主线程
            errors.append(exc)

    worker = threading.Thread(target=stream)
    worker.start()

    message_id = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        messages = client.get(
            f"/api/v1/assistant/sessions/{session['id']}/messages"
        ).json()["items"]
        assistant = [item for item in messages if item["role"] == "assistant"]
        if assistant:
            message_id = assistant[-1]["id"]
            break
        time.sleep(0.1)
    assert message_id, "assistant message was not created"

    cancelled = client.post(f"/api/v1/assistant/messages/{message_id}/cancel")
    assert cancelled.status_code == 200
    if cancelled.json()["cancelled"] is not True:
        pytest.skip("turn finished before cancel arrived; rerun for the cancel path")

    worker.join(timeout=60)
    assert not worker.is_alive(), "stream did not stop after cancel"
    assert not errors

    events = parse_sse(lines)
    done = [data for name, data in events if name == "done"]
    assert done and done[-1].get("cancelled") is True
    stored = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"]
    assistant = [item for item in stored if item["role"] == "assistant"][-1]
    assert assistant["status"] == "cancelled"


class _AuthErrorHandler(BaseHTTPRequestHandler):
    """模拟 Anthropic 兼容网关的 401；只用于验证错误映射。"""

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)
        body = json.dumps(
            {
                "type": "error",
                "error": {"type": "authentication_error", "message": "invalid x-api-key"},
            }
        ).encode("utf-8")
        self.send_response(401)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def auth_error_gateway():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AuthErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.slow
def test_live_error_401_is_sanitized(auth_error_gateway: str) -> None:
    """401 映射为 *_auth_error，错误文本不含 key。"""
    live_provider()  # 仍要求开关与凭据，避免误跑
    secret = "sk-live-DO-NOT-LOG-74c1"
    provider = Provider(
        id="llm_live_401",
        kind="anthropic",
        label="401 gateway",
        model=MODEL or "test-model",
        base_url=auth_error_gateway,
    )
    error = expect_llm_error(provider, secret)
    assert error.code == "anthropic_auth_error"
    assert "HTTP 401" in error.message
    assert secret not in error.message


@pytest.mark.slow
def test_live_error_bad_base_url_is_sanitized() -> None:
    """错误 baseUrl：连接失败也要脱敏，文本不含 key。"""
    live_provider()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    secret = "sk-live-DO-NOT-LOG-74c2"
    provider = Provider(
        id="llm_live_closed",
        kind="anthropic",
        label="closed port",
        model=MODEL or "test-model",
        base_url=f"http://127.0.0.1:{port}",
    )
    error = expect_llm_error(provider, secret)
    assert error.code.startswith("anthropic_")
    assert secret not in error.message
    assert "127.0.0.1" not in error.message


@pytest.mark.slow
def test_live_provider_probe_uses_custom_base_url(
    client: TestClient, providers_file
) -> None:
    """测试连接按钮必须打到自定义 baseUrl（代理），而不是官方端点。"""
    provider = save_provider(client)
    response = client.post(f"/api/v1/assistant/providers/{provider.id}/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True, body["message"]
    assert body["latencyMs"] is not None
    assert body["kind"] == "anthropic"
    assert body["model"] == provider.model


def test_base_url_rejects_query_credentials(tmp_path) -> None:
    """baseUrl 里夹带 token 会回显到前端，必须在保存前拒绝。"""
    from eclipse_health_backend.llm.providers import ProviderError, ProviderStore

    store = ProviderStore(tmp_path / "providers.json")
    with pytest.raises(ProviderError) as excinfo:
        store.upsert(
            "llm_query",
            {
                "kind": "anthropic",
                "baseUrl": "https://proxy.example.com/v1?api_key=sk-not-allowed",
            },
            api_key=None,
        )
    assert excinfo.value.code == "invalid_base_url"
    assert "sk-not-allowed" not in str(excinfo.value)

    saved = store.upsert(
        "llm_path",
        {"kind": "anthropic", "baseUrl": "https://proxy.example.com/anthropic/"},
        api_key=None,
    )
    assert saved.base_url == "https://proxy.example.com/anthropic"

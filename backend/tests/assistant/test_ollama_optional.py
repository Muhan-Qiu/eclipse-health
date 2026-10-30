"""Ollama 实测（可选）：默认跳过。

启用方式：

```powershell
$env:EH_TEST_OLLAMA=1
$env:EH_TEST_OLLAMA_MODEL="qwen3.5:9b"   # 可选，默认值见下
```

本机没有模型时只跳过，不失败；真实联调结果记录在
``reports/B4-08-report.md``。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from eclipse_health_backend.api.assistant import _test_ollama
from eclipse_health_backend.llm.providers import Provider

BASE_URL = os.environ.get("EH_TEST_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("EH_TEST_OLLAMA_MODEL", "qwen3.5:9b")


def _enabled() -> bool:
    return os.environ.get("EH_TEST_OLLAMA") == "1"


@pytest.mark.slow
def test_ollama_reachable() -> None:
    if not _enabled():
        pytest.skip("set EH_TEST_OLLAMA=1 to run against http://127.0.0.1:11434")
    try:
        response = httpx.get(f"{BASE_URL}/api/tags", timeout=5.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"ollama not running: {type(exc).__name__}")
    assert response.status_code == 200


@pytest.mark.slow
def test_ollama_capability_probe() -> None:
    if not _enabled():
        pytest.skip("set EH_TEST_OLLAMA=1 to run the capability probe")
    provider = Provider(
        id="llm_ollama_live",
        kind="ollama",
        label="Ollama",
        model=MODEL,
        base_url=BASE_URL,
    )
    probe = asyncio.run(_test_ollama(provider))
    if probe.available is False:
        pytest.skip(f"model {MODEL} is not installed: {probe.message}")
    assert probe.ok is True
    assert probe.supports_tools is True, probe.message
    assert probe.latency_ms is not None


@pytest.mark.slow
def test_ollama_turn_can_be_cancelled(client: TestClient, providers_file) -> None:
    """真实模型生成期间调用取消 API，必须落库 cancelled 并回发 done{cancelled}。"""
    if not _enabled():
        pytest.skip("set EH_TEST_OLLAMA=1 to run the live cancel test")
    provider = Provider(
        id="llm_live_cancel",
        kind="ollama",
        label="Ollama",
        model=MODEL,
        base_url=BASE_URL,
    )
    probe = asyncio.run(_test_ollama(provider))
    if not probe.ok:
        pytest.skip(f"ollama model unavailable: {probe.message}")

    assert (
        client.put(
            "/api/v1/assistant/providers/llm_live_cancel",
            json={"kind": "ollama", "label": "Ollama", "model": MODEL, "baseUrl": BASE_URL},
        ).status_code
        == 200
    )
    session = client.post(
        "/api/v1/assistant/sessions", json={"providerId": "llm_live_cancel"}
    ).json()

    lines: list[str] = []
    errors: list[BaseException] = []

    def stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/v1/assistant/sessions/{session['id']}/messages",
                json={
                    "content": "请用工具查一下我有几条记录，并详细解释。",
                    "providerId": "llm_live_cancel",
                },
            ) as response:
                lines.extend(response.iter_lines())
        except BaseException as exc:  # noqa: BLE001 - 线程内错误带回主线程断言
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
        time.sleep(0.2)
    assert message_id, "assistant message was not created"

    cancelled = client.post(f"/api/v1/assistant/messages/{message_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is True

    worker.join(timeout=60)
    assert not worker.is_alive(), "stream did not stop after cancel"
    assert not errors

    events = _parse_events(lines)
    done = [data for name, data in events if name == "done"]
    assert done and done[-1].get("cancelled") is True
    stored = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"]
    assistant = [item for item in stored if item["role"] == "assistant"][-1]
    assert assistant["status"] == "cancelled"
    # 取消前已经构造好的透明面板也要落库，用户仍能核对发送了什么。
    assert assistant["transparency"] is not None


def _parse_events(lines: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name: str | None = None
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif line == "" and name is not None:
            events.append((name, json.loads("\n".join(data) or "{}")))
            name, data = None, []
    return events

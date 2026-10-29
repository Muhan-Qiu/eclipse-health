"""取消、超时与工具调用上限（不经过 HTTP，直接驱动 agent）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider
from eclipse_health_backend.llm.tools import ToolBox


@pytest.fixture(autouse=True)
def _database(client) -> None:
    return None


def _provider() -> Provider:
    return Provider(id="llm_test", kind="mock", label="Test", model="mock-1")


class SlowAdapter(agent.ChatAdapter):
    def __init__(self, delay: float = 5.0) -> None:
        super().__init__(_provider(), None)
        self.delay = delay

    async def stream(self, messages, tools, cancel):  # type: ignore[no-untyped-def]
        await asyncio.sleep(self.delay)
        yield {"type": "token", "text": "late"}


class EndlessToolAdapter(agent.ChatAdapter):
    def __init__(self) -> None:
        super().__init__(_provider(), None)

    async def stream(self, messages, tools, cancel):  # type: ignore[no-untyped-def]
        yield {
            "type": "tool_calls",
            "calls": [{"id": "call_x", "name": "list_records", "args": {"limit": 1}}],
        }


def _run(adapter: agent.ChatAdapter, *, cancel: asyncio.Event, timeout_s: float) -> list[dict]:
    async def runner() -> list[dict]:
        events: list[dict] = []
        with session_scope() as session:
            toolbox = ToolBox(session, "mem_test")
            async for event in agent.stream_reply(
                provider=_provider(),
                adapter=adapter,
                messages=[{"role": "user", "content": "hi"}],
                toolbox=toolbox,
                transparency={},
                cancel=cancel,
                timeout_s=timeout_s,
            ):
                events.append(event)
        return events

    return asyncio.run(runner())


def test_turn_timeout() -> None:
    with pytest.raises(agent.TurnTimeout):
        _run(SlowAdapter(delay=5.0), cancel=asyncio.Event(), timeout_s=0.05)


def test_turn_cancelled() -> None:
    async def scenario() -> list[dict]:
        cancel = asyncio.Event()

        async def stop_soon() -> None:
            await asyncio.sleep(0.05)
            cancel.set()

        setter = asyncio.create_task(stop_soon())
        try:
            with session_scope() as session:
                events: list[dict] = []
                async for event in agent.stream_reply(
                    provider=_provider(),
                    adapter=SlowAdapter(delay=5.0),
                    messages=[{"role": "user", "content": "hi"}],
                    toolbox=ToolBox(session, "mem_test"),
                    transparency={},
                    cancel=cancel,
                    timeout_s=10.0,
                ):
                    events.append(event)
                return events
        finally:
            setter.cancel()

    with pytest.raises(agent.TurnCancelled):
        asyncio.run(scenario())


def test_tool_call_limit() -> None:
    events = _run(EndlessToolAdapter(), cancel=asyncio.Event(), timeout_s=2.0)
    tool_results = [event for event in events if event["event"] == "tool_result"]
    executed = [event for event in tool_results if event["data"]["ok"]]
    assert len(executed) == agent.MAX_TOOL_CALLS
    assert tool_results[-1]["data"]["ok"] is False
    assert "上限" in tool_results[-1]["data"]["resultSummary"]
    done = events[-1]
    assert done["event"] == "done"
    assert "上限" in done["data"]["content"]


def test_unknown_event_does_not_break_stream() -> None:
    class WeirdAdapter(agent.ChatAdapter):
        async def stream(self, messages: list[dict[str, Any]], tools, cancel):  # type: ignore[no-untyped-def]
            yield {"type": "usage", "tokens": 10}
            yield {"type": "token", "text": "ok"}

    events = _run(WeirdAdapter(_provider(), None), cancel=asyncio.Event(), timeout_s=2.0)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["content"] == "ok"

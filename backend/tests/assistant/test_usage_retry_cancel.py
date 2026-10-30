"""用量、重试与取消（B4-08）。

- mock 轮次必须产出 usage，并落到消息记录；
- 流式请求在「首字之前」失败时重试一次，已输出后不重试；
- 取消 API 优先停止活跃轮次，进程重启后的残留 streaming 记录直接修正。
"""

from __future__ import annotations

import asyncio

import pytest
from assistant_helpers import MOCK_PROVIDER_ID, stream_message
from fastapi.testclient import TestClient

from eclipse_health_backend.db import assistant_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider
from eclipse_health_backend.llm.tools import ToolBox
from eclipse_health_backend.llm.turns import TurnRegistry


@pytest.fixture(autouse=True)
def _database(client) -> None:
    return None


def _provider() -> Provider:
    return Provider(id="llm_test", kind="mock", label="Test", model="mock-1")


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


def test_mock_turn_reports_usage(client: TestClient, mock_provider: dict) -> None:
    session = client.post(
        "/api/v1/assistant/sessions", json={"providerId": MOCK_PROVIDER_ID}
    ).json()
    status, events = stream_message(
        client,
        session["id"],
        {"content": "你好", "providerId": MOCK_PROVIDER_ID},
    )
    assert status == 200
    done = events[-1][1]
    usage = done["usage"]
    assert usage is not None
    assert usage["promptTokens"] > 0
    assert usage["completionTokens"] > 0
    assert usage["totalTokens"] == usage["promptTokens"] + usage["completionTokens"]
    assert usage["source"] == "estimate"
    assert done["transparency"]["usage"] == usage
    assert done["durationMs"] >= 0

    stored = client.get(f"/api/v1/assistant/sessions/{session['id']}/messages").json()
    assistant = stored["items"][1]
    assert assistant["usage"] == usage
    assert assistant["durationMs"] == done["durationMs"]
    assert assistant["model"] == "mock-1"


class FlakyAdapter(agent.ChatAdapter):
    def __init__(self, *, fail_after_token: bool = False) -> None:
        super().__init__(_provider(), None)
        self.calls = 0
        self.fail_after_token = fail_after_token

    async def stream(self, messages, tools, cancel):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail_after_token and self.calls >= 1:
            yield {"type": "token", "text": "partial"}
            raise agent.LLMError("mock_server_error", "upstream exploded")
        if self.calls == 1:
            raise agent.LLMError("mock_server_error", "upstream exploded")
        yield {"type": "token", "text": "ok"}


def test_transient_error_retries_before_first_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "RETRY_BACKOFF_S", 0.01)
    adapter = FlakyAdapter()
    events = _run(adapter, cancel=asyncio.Event(), timeout_s=2.0)
    assert adapter.calls == 2
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["content"] == "ok"
    assert [event["data"]["text"] for event in events if event["event"] == "token"] == ["ok"]


def test_no_retry_after_partial_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "RETRY_BACKOFF_S", 0.01)
    adapter = FlakyAdapter(fail_after_token=True)
    with pytest.raises(agent.LLMError) as excinfo:
        _run(adapter, cancel=asyncio.Event(), timeout_s=2.0)
    assert excinfo.value.code == "mock_server_error"
    assert adapter.calls == 1


def test_turn_registry_cancel_stops_agent() -> None:
    class SlowAdapter(agent.ChatAdapter):
        async def stream(self, messages, tools, cancel):  # type: ignore[no-untyped-def]
            await asyncio.sleep(5)
            yield {"type": "token", "text": "late"}

    async def scenario() -> None:
        registry = TurnRegistry()
        cancel = registry.register("lmsg_1", "lsn_1")
        assert registry.is_active("lmsg_1")

        async def stop() -> None:
            await asyncio.sleep(0.05)
            assert registry.cancel("lmsg_1") is True

        task = asyncio.create_task(stop())
        try:
            with session_scope() as session:
                async for _event in agent.stream_reply(
                    provider=_provider(),
                    adapter=SlowAdapter(_provider(), None),
                    messages=[{"role": "user", "content": "hi"}],
                    toolbox=ToolBox(session, "mem_test"),
                    transparency={},
                    cancel=cancel,
                    timeout_s=10.0,
                ):
                    pass
        finally:
            task.cancel()
            registry.unregister("lmsg_1")

    with pytest.raises(agent.TurnCancelled):
        asyncio.run(scenario())


def _stale_streaming_message(client: TestClient) -> tuple[str, str]:
    session = client.post(
        "/api/v1/assistant/sessions", json={"providerId": MOCK_PROVIDER_ID}
    ).json()
    with session_scope() as db:
        row = assistant_repo.add_message(
            db,
            session_id=session["id"],
            role=assistant_repo.ROLE_ASSISTANT,
            content="partial",
            status=assistant_repo.STATUS_STREAMING,
            data={"providerId": MOCK_PROVIDER_ID},
        )
        return session["id"], row.id


def test_cancel_api_marks_stale_streaming_message(
    client: TestClient, mock_provider: dict
) -> None:
    session_id, message_id = _stale_streaming_message(client)
    response = client.post(f"/api/v1/assistant/messages/{message_id}/cancel")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cancelled"] is True
    assert body["status"] == "cancelled"

    messages = client.get(f"/api/v1/assistant/sessions/{session_id}/messages").json()
    assert messages["items"][0]["status"] == "cancelled"


def test_cancel_api_errors(client: TestClient, mock_provider: dict) -> None:
    session_id, message_id = _stale_streaming_message(client)
    # 已结束的消息：幂等返回当前状态
    client.post(f"/api/v1/assistant/messages/{message_id}/cancel")
    again = client.post(f"/api/v1/assistant/messages/{message_id}/cancel")
    assert again.status_code == 200
    assert again.json()["cancelled"] is False

    missing = client.post("/api/v1/assistant/messages/lmsg_missing/cancel")
    assert missing.status_code == 404

    with session_scope() as db:
        user_row = assistant_repo.add_message(
            db,
            session_id=session_id,
            role=assistant_repo.ROLE_USER,
            content="hi",
        )
        user_id = user_row.id
    invalid = client.post(f"/api/v1/assistant/messages/{user_id}/cancel")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_message_role"


def test_cancel_endpoint_hides_foreign_messages(
    client: TestClient, mock_provider: dict
) -> None:
    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    with session_scope() as db:
        foreign_session = assistant_repo.create_session(db, member_id=other["id"])
        foreign_message = assistant_repo.add_message(
            db,
            session_id=foreign_session.id,
            role=assistant_repo.ROLE_ASSISTANT,
            status=assistant_repo.STATUS_STREAMING,
        )
        foreign_id = foreign_message.id

    response = client.post(f"/api/v1/assistant/messages/{foreign_id}/cancel")
    assert response.status_code == 404
    assert response.json()["code"] == "assistant_message_not_found"

    missing = client.post("/api/v1/assistant/messages/lmsg_nope/cancel")
    assert missing.status_code == 404
    assert missing.json()["code"] == "assistant_message_not_found"

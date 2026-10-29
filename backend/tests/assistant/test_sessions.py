"""会话历史、SSE 主链路与透明面板（F1/F2/F4/F6）。"""

from __future__ import annotations

import json

from assistant_helpers import MOCK_PROVIDER_ID, parse_sse, stream_message
from fastapi.testclient import TestClient


def _create_session(client: TestClient, **payload) -> dict:
    body = {"providerId": MOCK_PROVIDER_ID, **payload}
    response = client.post("/api/v1/assistant/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _events(events):
    return [name for name, _data in events]


def test_mock_tool_loop_event_order(
    client: TestClient, mock_provider: dict, record_with_analysis: dict
) -> None:
    record = record_with_analysis["record"]
    session = _create_session(client, recordId=record["id"])
    status, events = stream_message(
        client,
        session["id"],
        {
            "content": "这条记录有什么异常？",
            "style": "brief",
            "providerId": MOCK_PROVIDER_ID,
            "recordId": record["id"],
        },
    )
    assert status == 200

    names = _events(events)
    tool_calls = [data for name, data in events if name == "tool_call"]
    assert [call["name"] for call in tool_calls] == [
        "list_records",
        "get_analysis",
        "get_measurements",
    ]
    assert names.count("tool_result") == 3
    assert names.count("citation") >= 3
    assert names[-1] == "done"
    assert names.index("tool_call") < names.index("done")

    done = events[-1][1]
    assert done["toolCalls"] == 3
    assert "平均心率 72" in done["content"]
    assert done["transparency"]["provider"]["kind"] == "mock"

    # 落库：user + assistant 两条，assistant 带工具调用与透明度
    stored = client.get(f"/api/v1/assistant/sessions/{session['id']}/messages").json()
    assert [item["role"] for item in stored["items"]] == ["user", "assistant"]
    assistant = stored["items"][1]
    assert assistant["status"] == "completed"
    assert assistant["content"] == done["content"]
    assert len(assistant["toolCalls"]) == 3
    assert assistant["transparency"]["provider"]["model"] == "mock-1"
    assert assistant["citations"]

    trace = assistant["toolCalls"][0]
    assert trace["name"] == "list_records"
    assert trace["args"] == {"limit": 5}
    assert trace["ok"] is True
    assert isinstance(trace["durationMs"], int)


def test_transparency_fields(
    client: TestClient, mock_provider: dict, record_with_analysis: dict
) -> None:
    record = record_with_analysis["record"]
    session = _create_session(client, recordId=record["id"])
    _status, events = stream_message(
        client,
        session["id"],
        {"content": "解释一下 HRV", "providerId": MOCK_PROVIDER_ID, "recordId": record["id"]},
    )
    transparency = events[-1][1]["transparency"]
    assert transparency["provider"]["kind"] == "mock"
    assert transparency["model"] == "mock-1"
    assert "record.id" in transparency["sentFields"]
    assert "analysis.summary" in transparency["sentFields"]
    assert "measurement.value" in transparency["sentFields"]
    assert "record.notes" in transparency["redactions"]
    assert "member.displayName" in transparency["redactions"]
    assert "signal.samples" in transparency["redactions"]
    assert transparency["approxTokens"] > 0
    assert transparency["recordIds"] == [record["id"]]
    assert transparency["analysisIds"] == [record_with_analysis["analysisId"]]
    assert transparency["includeNotes"] is False
    assert transparency["localOnly"] is True

    message_id = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"][1]["id"]
    fetched = client.get(f"/api/v1/assistant/messages/{message_id}/transparency")
    assert fetched.status_code == 200
    assert fetched.json()["approxTokens"] == transparency["approxTokens"]

    user_id = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"][0]["id"]
    missing = client.get(f"/api/v1/assistant/messages/{user_id}/transparency")
    assert missing.status_code == 404
    assert missing.json()["code"] == "transparency_not_available"


def test_include_notes_moves_field_into_sent(
    client: TestClient, mock_provider: dict, record_with_analysis: dict
) -> None:
    record = record_with_analysis["record"]
    session = _create_session(client, recordId=record["id"])
    _status, events = stream_message(
        client,
        session["id"],
        {
            "content": "结合我的备注看看",
            "providerId": MOCK_PROVIDER_ID,
            "recordId": record["id"],
            "includeNotes": True,
        },
    )
    transparency = events[-1][1]["transparency"]
    assert "record.notes" in transparency["sentFields"]
    assert "record.notes" not in transparency["redactions"]
    assert transparency["includeNotes"] is True


def test_session_without_records(
    client: TestClient, mock_provider: dict, empty_record: dict
) -> None:
    session = _create_session(client)
    _status, events = stream_message(
        client, session["id"], {"content": "我有几条记录？", "providerId": MOCK_PROVIDER_ID}
    )
    tool_calls = [data for name, data in events if name == "tool_call"]
    assert [call["name"] for call in tool_calls] == ["list_records"]
    done = events[-1][1]
    assert "还没有已完成的分析结果" in done["content"]
    assert done["transparency"]["recordIds"]  # 最近记录仍会作为摘要发送


def test_session_lifecycle(client: TestClient, mock_provider: dict) -> None:
    session = _create_session(client, title="我的会话")
    assert session["title"] == "我的会话"
    assert session["messageCount"] == 0

    listed = client.get("/api/v1/assistant/sessions")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == session["id"]

    detail = client.get(f"/api/v1/assistant/sessions/{session['id']}")
    assert detail.status_code == 200
    assert detail.json()["providerId"] == MOCK_PROVIDER_ID

    assert client.delete(f"/api/v1/assistant/sessions/{session['id']}").status_code == 204
    assert client.get(f"/api/v1/assistant/sessions/{session['id']}").status_code == 404
    assert client.get(f"/api/v1/assistant/sessions/{session['id']}/messages").status_code == 404


def test_title_comes_from_first_message(
    client: TestClient, mock_provider: dict, empty_record: dict
) -> None:
    session = _create_session(client)
    assert session["title"] == "新会话"
    stream_message(
        client,
        session["id"],
        {"content": "和上次比怎么样？", "providerId": MOCK_PROVIDER_ID},
    )
    updated = client.get("/api/v1/assistant/sessions").json()["items"][0]
    assert updated["title"] == "和上次比怎么样？"
    assert updated["messageCount"] == 2
    assert updated["hasNotes"] is False


def test_errors(
    client: TestClient,
    mock_provider: dict,
    default_member: dict,
    record_with_analysis: dict,
) -> None:
    session = _create_session(client)

    missing_provider = client.post(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        json={"content": "hi", "providerId": "llm_missing"},
    )
    assert missing_provider.status_code == 404
    assert missing_provider.json()["code"] == "provider_not_found"

    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    foreign = client.post(
        "/api/v1/records",
        json={
            "memberId": other["id"],
            "recordType": "org.eclipsehealth.ecg",
            "capturedAt": "2026-10-28T08:00:00Z",
            "timezone": "Asia/Shanghai",
            "source": {"kind": "file"},
            "samplingRate": 360.0,
            "leads": ["MLII"],
            "unit": "mV",
        },
    ).json()
    foreign_record = client.post(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        json={
            "content": "看看这条",
            "providerId": MOCK_PROVIDER_ID,
            "recordId": foreign["id"],
        },
    )
    assert foreign_record.status_code == 404
    assert foreign_record.json()["code"] == "record_not_found"

    no_key = client.put(
        "/api/v1/assistant/providers/llm_openai_nokey",
        json={"kind": "openai", "model": "gpt-4.1-mini"},
    )
    assert no_key.status_code == 200
    missing_key = client.post(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        json={"content": "hi", "providerId": "llm_openai_nokey"},
    )
    assert missing_key.status_code == 409
    assert missing_key.json()["code"] == "missing_api_key"


def test_stream_is_sse_text(
    client: TestClient, mock_provider: dict, record_with_analysis: dict
) -> None:
    session = _create_session(client)
    with client.stream(
        "POST",
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        json={"content": "你好", "providerId": MOCK_PROVIDER_ID},
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())
    events = parse_sse(lines)
    assert events
    assert json.dumps(events[-1][1], ensure_ascii=False)

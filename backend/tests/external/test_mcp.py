"""MCP stdio server：工具列表、参数 Schema 与一次工具调用（F3）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from eclipse_health_backend import mcp_server


def test_tool_list_and_schema() -> None:
    tools = asyncio.run(mcp_server.server.list_tools())
    by_name = {tool.name: tool for tool in tools}
    assert set(by_name) == {
        "list_records",
        "get_record",
        "get_analysis",
        "health_summary",
        "ask_assistant",
    }

    get_record = by_name["get_record"]
    assert get_record.input_schema["type"] == "object"
    assert get_record.input_schema["properties"]["record_id"]["type"] == "string"
    assert get_record.input_schema["required"] == ["record_id"]

    list_records = by_name["list_records"]
    assert list_records.input_schema["properties"]["limit"]["type"] == "integer"
    assert list_records.input_schema["properties"]["offset"]["type"] == "integer"

    ask = by_name["ask_assistant"]
    assert ask.input_schema["required"] == ["question"]


def test_tool_call_uses_http(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(
        method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        calls.append((method, path, kwargs))
        return {
            "record": {"id": "rec_test", "kind": "ecg"},
            "payload": None,
        }

    monkeypatch.setattr(mcp_server, "_request_json", fake_request)
    result = asyncio.run(
        mcp_server.server.call_tool("get_record", {"record_id": "rec_test"})
    )
    assert result.is_error is False
    body = json.loads(result.content[0].text)
    assert body["record"]["id"] == "rec_test"
    assert calls == [
        ("GET", "/external/records/rec_test", {}),
    ]


def test_ask_assistant_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(
        method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        assert method == "POST"
        assert path == "/external/openai/v1/chat/completions"
        assert kwargs["json_body"]["messages"][0]["content"] == "心率如何？"
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "平均心率 72 bpm。"}}
            ],
            "citations": [{"kind": "record", "id": "rec_1"}],
        }

    monkeypatch.setattr(mcp_server, "_request_json", fake_request)
    result = asyncio.run(
        mcp_server.server.call_tool("ask_assistant", {"question": "心率如何？"})
    )
    body = json.loads(result.content[0].text)
    assert body["content"] == "平均心率 72 bpm。"
    assert body["citations"][0]["id"] == "rec_1"


def test_api_error_maps_to_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        raise mcp_server.ExternalApiError(
            "invalid API key: EH_EXTERNAL_KEY is unknown or revoked", status_code=401
        )

    monkeypatch.setattr(mcp_server, "_request_json", failing)
    with pytest.raises(ToolError) as excinfo:
        asyncio.run(
            mcp_server.server.call_tool("get_record", {"record_id": "rec_test"})
        )
    assert "invalid API key" in str(excinfo.value)


def test_missing_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EH_EXTERNAL_KEY", raising=False)
    with pytest.raises(ToolError) as excinfo:
        asyncio.run(
            mcp_server.server.call_tool("health_summary", {"days": 7})
        )
    assert "EH_EXTERNAL_KEY" in str(excinfo.value)

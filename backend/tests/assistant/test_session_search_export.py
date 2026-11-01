"""会话搜索、重命名、消息分页与 Markdown 导出（B4-08）。"""

from __future__ import annotations

from assistant_helpers import MOCK_PROVIDER_ID, stream_message
from fastapi.testclient import TestClient


def _create(client: TestClient, title: str | None = None) -> dict:
    body: dict = {"providerId": MOCK_PROVIDER_ID}
    if title is not None:
        body["title"] = title
    response = client.post("/api/v1/assistant/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _send(client: TestClient, session_id: str, content: str) -> None:
    status, events = stream_message(
        client, session_id, {"content": content, "providerId": MOCK_PROVIDER_ID}
    )
    assert status == 200
    assert events[-1][0] == "done"


def test_search_by_title_and_first_message(client: TestClient, mock_provider: dict) -> None:
    titled = _create(client, "心率复查")
    first_message = _create(client, "夜间记录")
    _send(client, first_message["id"], "HRV 趋势怎么样")
    unrelated = _create(client, "晨起记录")
    _send(client, unrelated["id"], "今天状态")

    by_title = client.get("/api/v1/assistant/sessions", params={"q": "心率"}).json()
    assert [item["id"] for item in by_title["items"]] == [titled["id"]]
    assert by_title["query"] == "心率"

    by_first_message = client.get("/api/v1/assistant/sessions", params={"q": "HRV"}).json()
    assert [item["id"] for item in by_first_message["items"]] == [first_message["id"]]

    assert client.get("/api/v1/assistant/sessions", params={"q": "不存在"}).json()["items"] == []

    # LIKE 通配符按字面处理，不能把 % 当成“匹配全部”
    assert client.get("/api/v1/assistant/sessions", params={"q": "%"}).json()["items"] == []
    # 空搜索回到完整列表
    all_sessions = client.get("/api/v1/assistant/sessions", params={"q": "  "}).json()
    assert len(all_sessions["items"]) == 3


def test_rename_session(client: TestClient, mock_provider: dict) -> None:
    session = _create(client)
    renamed = client.patch(
        f"/api/v1/assistant/sessions/{session['id']}", json={"title": "  夜间 HRV  "}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "夜间 HRV"
    assert client.get(f"/api/v1/assistant/sessions/{session['id']}").json()["title"] == "夜间 HRV"

    blank = client.patch(
        f"/api/v1/assistant/sessions/{session['id']}", json={"title": "   "}
    )
    assert blank.status_code == 422
    assert blank.json()["code"] == "invalid_title"

    too_long = client.patch(
        f"/api/v1/assistant/sessions/{session['id']}", json={"title": "x" * 121}
    )
    assert too_long.status_code == 422

    missing = client.patch(
        "/api/v1/assistant/sessions/lsn_missing", json={"title": "x"}
    )
    assert missing.status_code == 404


def test_message_pagination(client: TestClient, mock_provider: dict) -> None:
    session = _create(client)
    for index in range(3):
        _send(client, session["id"], f"第 {index} 个问题")

    first = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        params={"limit": 2, "offset": 0, "order": "desc"},
    ).json()
    assert first["total"] == 6
    assert first["hasMore"] is True
    assert len(first["items"]) == 2
    assert first["items"][0]["role"] == "assistant"
    assert first["items"][1]["content"] == "第 2 个问题"

    second = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        params={"limit": 2, "offset": 2, "order": "desc"},
    ).json()
    third = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        params={"limit": 2, "offset": 4, "order": "desc"},
    ).json()
    assert third["hasMore"] is False

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(seen) == len(set(seen)) == 6

    ascending = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages",
        params={"limit": 2, "offset": 0, "order": "asc"},
    ).json()
    assert ascending["items"][0]["role"] == "user"
    assert ascending["items"][0]["content"] == "第 0 个问题"
    assert ascending["items"][1]["role"] == "assistant"


def test_export_markdown_redacts_tool_details(
    client: TestClient, mock_provider: dict, record_with_analysis: dict
) -> None:
    record = record_with_analysis["record"]
    session = _create(client, "导出测试")
    _send(client, session["id"], "这条记录有什么异常？")
    # 绑定记录后重新发一轮，让工具调用包含记录/分析
    status, _events = stream_message(
        client,
        session["id"],
        {
            "content": "再看一次",
            "providerId": MOCK_PROVIDER_ID,
            "recordId": record["id"],
        },
    )
    assert status == 200

    response = client.get(f"/api/v1/assistant/sessions/{session['id']}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="eclipse-health-assistant-')
    assert disposition.endswith('.md"')

    text = response.text
    assert text.startswith("# 导出测试")
    assert "## 用户" in text
    assert "## 助手" in text
    assert "list_records" in text
    assert "工具调用" in text
    assert "不含波形" in text
    # 默认不导出工具参数与原始返回
    assert '"limit"' not in text
    assert '"items"' not in text
    assert "resultSummary" not in text

    with_args = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/export",
        params={"includeToolArgs": "true"},
    )
    assert with_args.status_code == 200
    assert '"limit": 5' in with_args.text
    # 即便带参数也不含工具原始返回
    assert '"items"' not in with_args.text


def test_export_missing_session(client: TestClient, mock_provider: dict) -> None:
    response = client.get("/api/v1/assistant/sessions/lsn_missing/export")
    assert response.status_code == 404
    assert response.json()["code"] == "assistant_session_not_found"

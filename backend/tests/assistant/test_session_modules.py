"""本轮所选模块：会话/消息持久化、moduleIds 校验与透明面板。"""

from __future__ import annotations

from typing import Any

import pytest
from assistant_helpers import MOCK_PROVIDER_ID, stream_message
from fastapi.testclient import TestClient

from eclipse_health_backend.api import assistant as assistant_api
from eclipse_health_backend.db import assistant_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.repositories import ensure_default_member
from eclipse_health_backend.domain.errors import InvalidInputError
from eclipse_health_backend.modules import api as modules_api
from eclipse_health_backend.modules import contributions as contributions_module

_MODULES = [
    {
        "id": "mod.a",
        "name": "模块 A",
        "description": "说明",
        "type": "ai-tool",
        "enabled": True,
    },
    {
        "id": "mod.off",
        "name": "停用模块",
        "description": "",
        "type": "page",
        "enabled": False,
    },
]


class _FakeManager:
    def __init__(self, summaries: list[dict[str, Any]]) -> None:
        self._summaries = summaries
        self.engine = object()

    def list_modules(self) -> list[dict[str, Any]]:
        return list(self._summaries)


def _fake_contributions(_manager: Any, *, kind: str | None = None) -> dict[str, Any]:
    if kind == "tools":
        return {
            "type": kind,
            "items": [
                {
                    "moduleId": "mod.a",
                    "id": "echo.text",
                    "name": "回显",
                    "description": "回显文本",
                },
                {"moduleId": "mod.other", "id": "other.tool", "name": "其他"},
            ],
        }
    if kind == "pages":
        return {
            "type": kind,
            "items": [{"moduleId": "mod.a", "id": "overview", "title": "总览"}],
        }
    return {"type": kind, "items": []}


def test_session_module_ids_roundtrip(client: TestClient) -> None:
    with session_scope() as session:
        member = ensure_default_member(session)
        row = assistant_repo.create_session(
            session,
            member_id=member.id,
            module_ids=["mod.b", "", " mod.a ", "mod.b"],
        )
        assert assistant_repo.session_to_dict(row)["moduleIds"] == ["mod.b", "mod.a"]

        assistant_repo.touch_session(session, row, module_ids=["mod.c", "mod.c"])
        assert assistant_repo.session_to_dict(row)["moduleIds"] == ["mod.c"]


def test_message_module_ids_roundtrip(client: TestClient) -> None:
    with session_scope() as session:
        member = ensure_default_member(session)
        session_row = assistant_repo.create_session(session, member_id=member.id)
        message = assistant_repo.add_message(
            session,
            session_id=session_row.id,
            role=assistant_repo.ROLE_USER,
            content="hi",
            data={"moduleIds": ["mod.a"]},
        )
        assert assistant_repo.message_to_dict(message, [])["moduleIds"] == ["mod.a"]


def test_request_models_accept_module_ids() -> None:
    session_in = assistant_api.SessionIn(moduleIds=["mod.a"])
    message_in = assistant_api.MessageIn(
        content="hi", providerId="llm_mock_test", moduleIds=["mod.a"]
    )
    assert session_in.moduleIds == ["mod.a"]
    assert message_in.moduleIds == ["mod.a"]


def test_resolve_module_ids_validates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _FakeManager(_MODULES)
    monkeypatch.setattr(modules_api, "get_manager", lambda: manager)

    assert assistant_api._resolve_module_ids(["mod.a", "mod.a"]) == ["mod.a"]

    with pytest.raises(InvalidInputError) as missing:
        assistant_api._resolve_module_ids(["mod.unknown"])
    assert missing.value.code == "module_not_found"

    with pytest.raises(InvalidInputError) as disabled:
        assistant_api._resolve_module_ids(["mod.off"])
    assert disabled.value.code == "module_disabled"


def test_resolve_module_ids_degrades_when_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Any:
        raise RuntimeError("module system unavailable")

    monkeypatch.setattr(modules_api, "get_manager", broken)
    assert assistant_api._resolve_module_ids(["mod.a"]) == []


def test_selected_module_briefs(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _FakeManager(_MODULES)
    monkeypatch.setattr(modules_api, "get_manager", lambda: manager)
    monkeypatch.setattr(contributions_module, "collect_contributions", _fake_contributions)

    assert assistant_api._selected_module_briefs(["mod.a"]) == [
        {
            "id": "mod.a",
            "name": "模块 A",
            "description": "说明",
            "type": "ai-tool",
            "tools": [{"id": "echo.text", "name": "回显", "description": "回显文本"}],
            "pages": [{"id": "overview", "title": "总览"}],
        }
    ]


def test_create_session_with_module_ids(
    client: TestClient, mock_provider: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modules_api, "get_manager", lambda: _FakeManager(_MODULES))
    response = client.post(
        "/api/v1/assistant/sessions",
        json={
            "providerId": MOCK_PROVIDER_ID,
            "moduleIds": ["mod.a", "", "mod.a"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["moduleIds"] == ["mod.a"]


def test_create_session_rejects_unknown_module(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modules_api, "get_manager", lambda: _FakeManager(_MODULES))
    response = client.post(
        "/api/v1/assistant/sessions",
        json={"moduleIds": ["mod.unknown"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "module_not_found"


def test_send_message_records_module_ids(
    client: TestClient, mock_provider: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modules_api, "get_manager", lambda: _FakeManager(_MODULES))
    monkeypatch.setattr(contributions_module, "collect_contributions", _fake_contributions)

    session = client.post(
        "/api/v1/assistant/sessions", json={"providerId": MOCK_PROVIDER_ID}
    ).json()
    status, events = stream_message(
        client,
        session["id"],
        {
            "content": "你好",
            "providerId": MOCK_PROVIDER_ID,
            "moduleIds": ["mod.a"],
        },
    )
    assert status == 200

    done = events[-1][1]
    assert done["transparency"]["selectedModules"] == ["mod.a"]
    assert done["transparency"]["selectedModuleTools"] == ["echo.text"]

    stored = client.get(
        f"/api/v1/assistant/sessions/{session['id']}/messages"
    ).json()["items"]
    assert [item["moduleIds"] for item in stored] == [["mod.a"], ["mod.a"]]

"""A8 自定义仪表盘卡片：CRUD、白名单、聚合、草稿与助手工具。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.llm.tools import ToolBox


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _health_record(
    client: TestClient,
    member_id: str,
    kind: str,
    value: Any,
    *,
    unit: str = "1",
    captured_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict:
    payload = {"value": value, "unit": unit, "startAt": captured_at or _iso(0)}
    if extra:
        payload.update(extra)
    body = {
        "memberId": member_id,
        "recordType": f"org.eclipsehealth.health.{kind}",
        "capturedAt": captured_at or _iso(0),
        "timezone": "UTC",
        "source": {"kind": "import"},
        "unit": unit,
        "payload": payload,
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _create_card(
    client: TestClient,
    member_id: str,
    *,
    kind: str = "spo2",
    aggregation: str = "latest",
    window_days: int = 30,
    view: str = "stat",
    title: str = "Blood oxygen",
    unit: str | None = None,
) -> dict:
    body = {
        "memberId": member_id,
        "title": title,
        "kind": kind,
        "aggregation": aggregation,
        "windowDays": window_days,
        "view": view,
        "unit": unit,
    }
    response = client.post("/api/v1/dashboard/cards", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _card_data(client: TestClient, member_id: str, card_id: str) -> dict:
    response = client.get(
        f"/api/v1/dashboard/cards/{card_id}/data", params={"memberId": member_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_templates_include_required_kinds(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/card-templates")
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert {
        "stress-latest",
        "stress-trend",
        "spo2-latest",
        "spo2-trend",
        "blood-pressure-latest",
        "blood-pressure-trend",
        "exercise-weekly",
        "sleep-duration",
    } <= set(items)
    assert items["exercise-weekly"]["aggregation"] == "sum"
    assert items["sleep-duration"]["kind"] == "sleep"


def test_card_field_whitelist(client: TestClient, default_member: dict) -> None:
    base = {
        "memberId": default_member["id"],
        "title": "X",
        "kind": "spo2",
        "aggregation": "latest",
        "windowDays": 30,
        "view": "stat",
    }

    invalid_kind = client.post(
        "/api/v1/dashboard/cards", json={**base, "kind": "arbitrary-sql"}
    )
    assert invalid_kind.status_code == 422

    invalid_aggregation = client.post(
        "/api/v1/dashboard/cards", json={**base, "aggregation": "median"}
    )
    assert invalid_aggregation.status_code == 422

    invalid_view = client.post(
        "/api/v1/dashboard/cards", json={**base, "view": "iframe"}
    )
    assert invalid_view.status_code == 422

    extra_field = client.post(
        "/api/v1/dashboard/cards", json={**base, "script": "alert(1)"}
    )
    assert extra_field.status_code == 422

    too_long_window = client.post(
        "/api/v1/dashboard/cards", json={**base, "windowDays": 9999}
    )
    assert too_long_window.status_code == 422


def test_card_crud_and_data(client: TestClient, default_member: dict) -> None:
    member_id = default_member["id"]
    _health_record(client, member_id, "spo2", 97, unit="%", captured_at=_iso(2))
    _health_record(client, member_id, "spo2", 98, unit="%", captured_at=_iso(1))

    card = _create_card(client, member_id)
    assert card["id"].startswith("dcr_")
    assert card["kind"] == "spo2"
    assert card["createdBy"] == "user"

    data = _card_data(client, member_id, card["id"])
    assert data["value"] == 98
    assert data["unit"] == "%"
    assert data["unitSource"] == "kind"
    assert data["hasData"] is True
    assert len(data["series"]) == 2

    listed = client.get(
        "/api/v1/dashboard/cards", params={"memberId": member_id, "includeData": "true"}
    ).json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["data"]["value"] == 98

    patched = client.patch(
        f"/api/v1/dashboard/cards/{card['id']}",
        json={"title": "SpO2", "view": "line", "windowDays": 7},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "SpO2"
    assert patched.json()["view"] == "line"

    deleted = client.delete(f"/api/v1/dashboard/cards/{card['id']}")
    assert deleted.status_code == 204
    assert client.get(
        "/api/v1/dashboard/cards", params={"memberId": member_id}
    ).json()["items"] == []


def test_aggregations_and_empty_state(client: TestClient, default_member: dict) -> None:
    member_id = default_member["id"]
    for days, steps in ((3, 1000), (2, 2000), (1, 3000)):
        _health_record(
            client, member_id, "steps", steps, unit="count", captured_at=_iso(days)
        )

    expected = {"latest": 3000, "avg": 2000, "min": 1000, "max": 3000, "sum": 6000}
    for aggregation, value in expected.items():
        card = _create_card(
            client,
            member_id,
            kind="steps",
            aggregation=aggregation,
            window_days=30,
            view="sparkline",
            title=f"steps-{aggregation}",
        )
        data = _card_data(client, member_id, card["id"])
        assert data["value"] == value, aggregation
        assert data["hasData"] is True

    count_card = _create_card(
        client,
        member_id,
        kind="steps",
        aggregation="count",
        title="steps-count",
    )
    count_data = _card_data(client, member_id, count_card["id"])
    assert count_data["value"] == 3
    assert count_data["unit"] == "count"

    empty_card = _create_card(client, member_id, kind="heart-rate", title="hr")
    empty_data = _card_data(client, member_id, empty_card["id"])
    assert empty_data["value"] is None
    assert empty_data["hasData"] is False
    assert empty_data["series"] == []
    assert empty_data["missingReason"] == "no_data"


def test_blood_pressure_pair(client: TestClient, default_member: dict) -> None:
    member_id = default_member["id"]
    _health_record(
        client,
        member_id,
        "blood-pressure",
        {"systolic": 121, "diastolic": 79},
        unit="mmHg",
        captured_at=_iso(1),
    )
    card = _create_card(
        client,
        member_id,
        kind="blood-pressure",
        aggregation="latest",
        title="BP",
    )
    data = _card_data(client, member_id, card["id"])
    assert data["value"] == 121
    assert data["secondaryValue"] == 79
    assert data["unit"] == "mmHg"


def test_exercise_and_sleep_duration_are_minutes(
    client: TestClient, default_member: dict
) -> None:
    member_id = default_member["id"]
    _health_record(
        client,
        member_id,
        "exercise",
        None,
        unit="min",
        captured_at=_iso(1),
        extra={"durationSec": 3600},
    )
    _health_record(
        client,
        member_id,
        "sleep",
        "asleep",
        unit="min",
        captured_at=_iso(1),
        extra={"startAt": _iso(1.5), "endAt": _iso(1), "durationSec": 1800},
    )

    exercise = _create_card(
        client,
        member_id,
        kind="exercise",
        aggregation="sum",
        view="bar",
        title="Exercise",
    )
    exercise_data = _card_data(client, member_id, exercise["id"])
    assert exercise_data["value"] == 60
    assert exercise_data["unit"] == "min"

    sleep = _create_card(
        client,
        member_id,
        kind="sleep",
        aggregation="avg",
        view="line",
        title="Sleep",
    )
    sleep_data = _card_data(client, member_id, sleep["id"])
    assert sleep_data["value"] == 30


def test_missing_unit_is_explicit(client: TestClient, default_member: dict) -> None:
    member_id = default_member["id"]
    _health_record(
        client,
        member_id,
        "stress",
        42,
        unit="1",
        captured_at=_iso(0),
        extra={"unit": ""},
    )
    card = _create_card(client, member_id, kind="stress", title="Stress", unit=None)
    data = _card_data(client, member_id, card["id"])
    assert data["value"] == 42
    assert data["unit"] is None
    assert data["unitSource"] == "missing"


def test_draft_confirm_and_discard(client: TestClient, default_member: dict) -> None:
    member_id = default_member["id"]
    fields = {
        "title": "SpO2 trend",
        "kind": "spo2",
        "aggregation": "avg",
        "windowDays": 30,
        "view": "line",
    }
    created = client.post(
        "/api/v1/dashboard/card-drafts",
        json=fields,
        params={"memberId": member_id},
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["id"].startswith("ddr_")
    assert draft["preview"]["hasData"] is False
    assert client.get(
        "/api/v1/dashboard/cards", params={"memberId": member_id}
    ).json()["items"] == []

    confirmed = client.post(
        f"/api/v1/dashboard/card-drafts/{draft['id']}/confirm",
        params={"memberId": member_id},
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["title"] == "SpO2 trend"
    assert client.get(
        "/api/v1/dashboard/card-drafts", params={"memberId": member_id}
    ).json()["items"] == []

    second = client.post(
        "/api/v1/dashboard/card-drafts",
        json=fields,
        params={"memberId": member_id},
    ).json()
    discarded = client.delete(
        f"/api/v1/dashboard/card-drafts/{second['id']}", params={"memberId": member_id}
    )
    assert discarded.status_code == 204


def test_cards_are_member_scoped(client: TestClient, default_member: dict) -> None:
    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    card = _create_card(client, other["id"], title="Other's card")

    visible = client.get(
        "/api/v1/dashboard/cards", params={"memberId": default_member["id"]}
    ).json()
    assert visible["items"] == []

    denied = client.delete(
        f"/api/v1/dashboard/cards/{card['id']}",
        params={"memberId": default_member["id"]},
    )
    assert denied.status_code == 404


def _call_tool(member_id: str, name: str, args: dict[str, Any] | None = None) -> dict:
    with session_scope() as session:
        return ToolBox(session, member_id).execute(name, args or {})


def test_assistant_tools_create_draft_then_confirm(
    client: TestClient, default_member: dict
) -> None:
    member_id = default_member["id"]
    _health_record(client, member_id, "spo2", 99, unit="%", captured_at=_iso(0))

    templates = _call_tool(member_id, "list_card_templates")
    assert templates["ok"] is True
    assert templates["result"]["count"] >= 8

    created = _call_tool(
        member_id,
        "create_dashboard_card",
        {"kind": "spo2", "aggregation": "latest", "view": "stat", "windowDays": 14},
    )
    assert created["ok"] is True, created
    draft_id = created["result"]["draftId"]
    assert created["result"]["saved"] is False
    assert created["result"]["preview"]["value"] == 99
    assert client.get(
        "/api/v1/dashboard/cards", params={"memberId": member_id}
    ).json()["items"] == []

    confirmed = _call_tool(
        member_id, "confirm_dashboard_card", {"draftId": draft_id}
    )
    assert confirmed["ok"] is True, confirmed
    assert confirmed["result"]["saved"] is True
    cards = client.get(
        "/api/v1/dashboard/cards", params={"memberId": member_id}
    ).json()["items"]
    assert len(cards) == 1
    assert cards[0]["createdBy"] == "agent"

    invalid = _call_tool(
        member_id, "create_dashboard_card", {"kind": "drop table", "aggregation": "latest"}
    )
    assert invalid["ok"] is False
    assert invalid["result"]["error"]["code"] == "INVALID_ARGUMENT"

"""运动记录 CRUD、过滤、软删除与校验。"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/exercises"
RECORD_TYPE = "org.eclipsehealth.health.exercise"


def _post(client: TestClient, **overrides):
    body = {"activity": "walk", "durationSec": 1800, "startAt": "2026-10-20T08:00:00+08:00"}
    body.update(overrides)
    return client.post(BASE, json=body)


def test_create_minimal(client: TestClient, default_member: dict) -> None:
    response = _post(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["activity"] == "walk"
    assert body["durationSec"] == 1800
    assert body["distanceKm"] is None
    assert body["intensity"] is None
    assert body["subjective"] is None
    assert body["notes"] == ""
    assert body["source"] == "manual"
    assert body["memberId"] == default_member["id"]


def test_create_full_fields(client: TestClient) -> None:
    response = _post(
        client,
        activity="run",
        durationSec=2700,
        distanceKm=5.2,
        intensity="vigorous",
        subjective="吃力",
        notes="傍晚公园",
        source="manual",
        timezone="Asia/Shanghai",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["activity"] == "run"
    assert body["distanceKm"] == 5.2
    assert body["intensity"] == "vigorous"
    assert body["subjective"] == "吃力"
    assert body["notes"] == "傍晚公园"


def test_invalid_duration_and_distance(client: TestClient) -> None:
    assert _post(client, durationSec=0).status_code == 422
    assert _post(client, durationSec=-5).status_code == 422
    assert _post(client, distanceKm=-1).status_code == 422
    assert _post(client, intensity="extreme").status_code == 422
    assert _post(client, subjective="很好").status_code == 422
    assert client.post(BASE, json={"activity": "walk", "startAt": "2026-10-20T08:00:00Z"}).status_code == 422
    assert _post(client, durationSec=60, unexpected=True).status_code == 422


def test_invalid_timezone(client: TestClient) -> None:
    response = _post(client, timezone="Mars/Olympus")
    assert response.status_code == 422
    assert response.json()["code"] == "exercise_invalid"


def test_list_order_filter_and_pagination(client: TestClient) -> None:
    _post(client, activity="walk", startAt="2026-10-01T08:00:00Z")
    _post(client, activity="run", startAt="2026-10-05T08:00:00Z")
    _post(client, activity="run", startAt="2026-10-09T08:00:00Z")

    page = client.get(BASE).json()
    assert page["total"] == 3
    assert [item["activity"] for item in page["items"]] == ["run", "run", "walk"]

    runs = client.get(BASE, params={"activity": "run"}).json()
    assert runs["total"] == 2

    window = client.get(
        BASE,
        params={"from": "2026-10-05T00:00:00Z", "to": "2026-10-09T23:59:59Z"},
    ).json()
    assert window["total"] == 2

    first = client.get(BASE, params={"limit": 1, "offset": 0}).json()
    second = client.get(BASE, params={"limit": 1, "offset": 1}).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_patch_and_clear_optional_fields(client: TestClient) -> None:
    created = _post(client, distanceKm=3.0, intensity="low", notes="morning").json()
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={
            "activity": "cycle",
            "durationSec": 3600,
            "distanceKm": 12.5,
            "intensity": "moderate",
            "subjective": "适中",
            "notes": "afternoon",
            "startAt": "2026-10-21T09:00:00+08:00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["activity"] == "cycle"
    assert body["distanceKm"] == 12.5
    assert body["subjective"] == "适中"
    assert body["startAt"].startswith("2026-10-21T09:00:00")

    cleared = client.patch(
        f"{BASE}/{created['id']}",
        json={"distanceKm": None, "intensity": None, "subjective": None},
    )
    assert cleared.status_code == 200, cleared.text
    cleared_body = cleared.json()
    assert cleared_body["distanceKm"] is None
    assert cleared_body["intensity"] is None
    assert cleared_body["subjective"] is None
    assert cleared_body["notes"] == "afternoon"


def test_delete_is_soft(client: TestClient) -> None:
    created = _post(client).json()
    assert client.delete(f"{BASE}/{created['id']}").status_code == 204
    assert client.get(BASE).json()["total"] == 0
    assert client.delete(f"{BASE}/{created['id']}").status_code == 404
    assert client.patch(f"{BASE}/{created['id']}", json={"notes": "x"}).status_code == 404

    records = client.get(
        "/api/v1/records",
        params={"recordType": RECORD_TYPE, "includeDeleted": "true"},
    ).json()
    assert records["total"] == 1


def test_is_core_record_without_signal(client: TestClient) -> None:
    created = _post(client, notes="swim").json()
    records = client.get("/api/v1/records", params={"recordType": RECORD_TYPE}).json()
    assert records["total"] == 1
    record = records["items"][0]
    assert record["id"] == created["id"]
    assert record["signalIds"] == []
    assert record["source"]["kind"] == "manual"
    assert record["payload"]["durationSec"] == 1800
    assert record["payload"]["activity"] == "walk"


def test_unknown_member(client: TestClient) -> None:
    response = _post(client, memberId="mem_missing")
    assert response.status_code == 404
    assert response.json()["code"] == "member_not_found"


def test_empty_first_run(client: TestClient) -> None:
    page = client.get(BASE).json()
    assert page == {"items": [], "total": 0, "limit": 20, "offset": 0}

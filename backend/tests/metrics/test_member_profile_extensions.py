"""G3 · 健康档案新增静息心率与睡眠时间字段。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _url(member: dict) -> str:
    return f"/api/v1/members/{member['id']}"


def test_resting_heart_rate_bounds(client: TestClient, default_member: dict) -> None:
    url = _url(default_member)
    assert client.patch(url, json={"restingHeartRate": 30}).status_code == 200
    assert client.patch(url, json={"restingHeartRate": 200}).status_code == 200
    assert client.patch(url, json={"restingHeartRate": 29}).status_code == 422
    assert client.patch(url, json={"restingHeartRate": 201}).status_code == 422
    assert client.patch(url, json={"restingHeartRate": 72}).json()["restingHeartRate"] == 72
    assert client.patch(url, json={"restingHeartRate": None}).json()["restingHeartRate"] is None


def test_sleep_clock_and_timezone(client: TestClient, default_member: dict) -> None:
    url = _url(default_member)
    response = client.patch(
        url,
        json={
            "sleepStart": "23:30",
            "sleepEnd": "07:15",
            "sleepTimezone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sleepStart"] == "23:30"
    assert body["sleepEnd"] == "07:15"
    assert body["sleepTimezone"] == "Asia/Shanghai"


def test_sleep_iso_and_partial(client: TestClient, default_member: dict) -> None:
    url = _url(default_member)
    response = client.patch(
        url,
        json={"sleepStart": "2026-10-30T23:30:00+08:00"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sleepStart"].startswith("2026-10-30T23:30:00")
    assert body["sleepEnd"] is None

    cleared = client.patch(url, json={"sleepStart": None, "sleepEnd": "06:45"})
    assert cleared.status_code == 200
    assert cleared.json()["sleepStart"] is None
    assert cleared.json()["sleepEnd"] == "06:45"


def test_sleep_invalid_values(client: TestClient, default_member: dict) -> None:
    url = _url(default_member)
    for value in ["25:00", "7:15", "23:60", "midnight", "2026-13-01T23:30:00Z"]:
        assert client.patch(url, json={"sleepStart": value}).status_code == 422, value
    bad_tz = client.patch(url, json={"sleepTimezone": "Mars/Olympus"})
    assert bad_tz.status_code == 422


def test_existing_fields_still_edit(client: TestClient, default_member: dict) -> None:
    url = _url(default_member)
    body = client.patch(
        url,
        json={
            "birthYear": 1992,
            "heightCm": 170,
            "weightKg": 65,
            "conditions": ["偏头痛"],
            "medications": ["布洛芬"],
            "notes": "夜班",
            "restingHeartRate": 58,
            "sleepStart": "00:10",
            "sleepEnd": "07:40",
        },
    ).json()
    assert body["birthYear"] == 1992
    assert body["conditions"] == ["偏头痛"]
    assert body["restingHeartRate"] == 58
    assert body["sleepStart"] == "00:10"

"""B4-07 · 健康档案（Member）编辑与上限校验。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_update_profile_fields(client: TestClient, default_member: dict) -> None:
    response = client.patch(
        f"/api/v1/members/{default_member['id']}",
        json={
            "birthYear": 1990,
            "sex": "female",
            "heightCm": 165,
            "weightKg": 58.5,
            "conditions": ["高血压"],
            "medications": ["氨氯地平"],
            "notes": "早晨测量",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["birthYear"] == 1990
    assert body["sex"] == "female"
    assert body["heightCm"] == 165
    assert body["weightKg"] == 58.5
    assert body["conditions"] == ["高血压"]
    assert body["medications"] == ["氨氯地平"]
    assert body["notes"] == "早晨测量"

    # 清空可选字段
    cleared = client.patch(
        f"/api/v1/members/{default_member['id']}",
        json={"birthYear": None, "conditions": [], "notes": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["birthYear"] is None
    assert cleared.json()["conditions"] == []
    assert cleared.json()["notes"] == ""


def test_profile_limits(client: TestClient, default_member: dict) -> None:
    url = f"/api/v1/members/{default_member['id']}"
    too_many = client.patch(url, json={"conditions": [f"c{index}" for index in range(33)]})
    assert too_many.status_code == 422

    long_notes = client.patch(url, json={"notes": "x" * 4001})
    assert long_notes.status_code == 422

    bad_year = client.patch(url, json={"birthYear": 1800})
    assert bad_year.status_code == 422

    bad_weight = client.patch(url, json={"weightKg": 600})
    assert bad_weight.status_code == 422


def test_profile_unknown_member(client: TestClient) -> None:
    response = client.patch("/api/v1/members/mem_missing", json={"sex": "male"})
    assert response.status_code == 404

from __future__ import annotations


def test_default_member_is_created(client) -> None:
    response = client.get("/api/v1/members")
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1
    assert members[0]["displayName"] == "本人"
    assert members[0]["id"].startswith("mem_")
    assert members[0]["schema"] == "org.eclipsehealth.member/1"


def test_create_and_get_member(client) -> None:
    response = client.post(
        "/api/v1/members",
        json={"displayName": "家人", "birthYear": 1960, "sex": "male", "heightCm": 172},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["birthYear"] == 1960

    fetched = client.get(f"/api/v1/members/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_patch_member(client, default_member: dict) -> None:
    response = client.patch(
        f"/api/v1/members/{default_member['id']}",
        json={"displayName": "我", "weightKg": 60.5, "conditions": ["高血压"]},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["displayName"] == "我"
    assert updated["weightKg"] == 60.5
    assert updated["conditions"] == ["高血压"]
    assert updated["updatedAt"] >= default_member["updatedAt"]


def test_get_unknown_member_returns_structured_404(client) -> None:
    response = client.get("/api/v1/members/mem_00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "member_not_found"
    assert body["message"]
    assert body["details"]["id"].startswith("mem_")


def test_member_validation_error_shape(client) -> None:
    response = client.post("/api/v1/members", json={"displayName": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"]
    assert isinstance(body["details"], list)


def test_member_rejects_unknown_field(client) -> None:
    response = client.post("/api/v1/members", json={"displayName": "x", "bloodType": "A"})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"

"""D1：收藏字段与 favorite 筛选（B5-01）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from helpers import create_record

API = "/api/v1"


def test_favorite_defaults_to_false(client: TestClient, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    assert record["favorite"] is False

    page = client.get(f"{API}/records").json()
    assert page["items"][0]["favorite"] is False


def test_patch_favorite_only(client: TestClient, default_member: dict) -> None:
    record = create_record(client, default_member["id"], notes="保留")
    response = client.patch(
        f"{API}/records/{record['id']}", json={"favorite": True}
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["favorite"] is True
    assert updated["notes"] == "保留"
    assert updated["tags"] == record["tags"]

    fetched = client.get(f"{API}/records/{record['id']}").json()
    assert fetched["favorite"] is True


def test_favorite_filter_paginates_consistently(
    client: TestClient, default_member: dict
) -> None:
    records = [
        create_record(client, default_member["id"], notes=f"记录 {index}")
        for index in range(3)
    ]
    for record in records[:2]:
        client.patch(f"{API}/records/{record['id']}", json={"favorite": True})

    favorites = client.get(f"{API}/records", params={"favorite": True}).json()
    assert favorites["total"] == 2
    assert {item["id"] for item in favorites["items"]} == {
        records[0]["id"],
        records[1]["id"],
    }

    page = client.get(
        f"{API}/records", params={"favorite": True, "limit": 1, "offset": 1}
    ).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] in {records[0]["id"], records[1]["id"]}

    others = client.get(f"{API}/records", params={"favorite": False}).json()
    assert others["total"] == 1
    assert others["items"][0]["id"] == records[2]["id"]

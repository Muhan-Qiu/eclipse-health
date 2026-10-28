from __future__ import annotations

from helpers import make_record_body, sine_samples


def test_create_record_without_signal(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"], notes="静息")
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    record = response.json()

    assert record["id"].startswith("rec_")
    assert record["schema"] == "org.eclipsehealth.record/1"
    assert record["signalIds"] == []
    assert record["notes"] == "静息"
    assert record["deletedAt"] is None
    assert record["samplingRate"] == 500.0
    assert record["createdAt"] == record["updatedAt"]

    fetched = client.get(f"/api/v1/records/{record['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == record


def test_create_record_with_signal_derives_metadata(client, default_member: dict) -> None:
    samples = sine_samples(n=500, fs=500.0)
    body = make_record_body(default_member["id"])
    body.pop("samplingRate")
    body.pop("leads")
    body["signal"] = {"lead": "I", "fs": 500.0, "samples": samples.tolist()}

    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    record = response.json()

    assert record["leads"] == ["I"]
    assert record["samplingRate"] == 500.0
    assert abs(record["durationSec"] - 1.0) < 1e-9
    assert len(record["signalIds"]) == 1
    assert record["signalIds"][0].startswith("sig_")


def test_record_creation_validates_member(client) -> None:
    body = make_record_body("mem_00000000-0000-0000-0000-000000000000")
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 404
    assert response.json()["code"] == "member_not_found"


def test_record_payload_is_stored_separately(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"], payload={"channelCount": 8, "montage": "10-20"})
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201
    record = response.json()
    assert record["payload"] == {"channelCount": 8, "montage": "10-20"}

    fetched = client.get(f"/api/v1/records/{record['id']}").json()
    assert fetched["payload"] == record["payload"]


def test_list_records_pagination_and_ordering(client, default_member: dict) -> None:
    member_id = default_member["id"]
    for hour in (8, 9, 10):
        body = make_record_body(member_id, capturedAt=f"2026-10-28T{hour:02d}:00:00Z")
        assert client.post("/api/v1/records", json=body).status_code == 201

    page = client.get("/api/v1/records", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert page["limit"] == 2
    assert len(page["items"]) == 2
    assert page["items"][0]["capturedAt"] > page["items"][1]["capturedAt"]

    tail = client.get("/api/v1/records", params={"limit": 2, "offset": 2}).json()
    assert len(tail["items"]) == 1


def test_list_records_filters(client, default_member: dict) -> None:
    member_id = default_member["id"]
    client.post("/api/v1/records", json=make_record_body(member_id))
    client.post(
        "/api/v1/records",
        json=make_record_body(
            member_id, recordType="io.github.demo.ppg", moduleId="io.github.demo"
        ),
    )
    client.post(
        "/api/v1/records",
        json=make_record_body(member_id, capturedAt="2026-10-29T08:00:00Z"),
    )

    by_type = client.get(
        "/api/v1/records", params={"recordType": "io.github.demo.ppg"}
    ).json()
    assert by_type["total"] == 1

    by_module = client.get("/api/v1/records", params={"moduleId": "io.github.demo"}).json()
    assert by_module["total"] == 1

    by_time = client.get(
        "/api/v1/records", params={"capturedFrom": "2026-10-28T12:00:00Z"}
    ).json()
    assert by_time["total"] == 1

    by_member = client.get(
        "/api/v1/records", params={"memberId": member_id}
    ).json()
    assert by_member["total"] == 3


def test_soft_delete_hides_record(client, default_member: dict) -> None:
    created = client.post(
        "/api/v1/records", json=make_record_body(default_member["id"])
    ).json()
    record_id = created["id"]

    assert client.delete(f"/api/v1/records/{record_id}").status_code == 204
    assert client.get(f"/api/v1/records/{record_id}").status_code == 404

    listing = client.get("/api/v1/records").json()
    assert listing["total"] == 0

    with_deleted = client.get("/api/v1/records", params={"includeDeleted": True}).json()
    assert with_deleted["total"] == 1
    assert with_deleted["items"][0]["deletedAt"] is not None

    # 再删一次视为已不存在
    assert client.delete(f"/api/v1/records/{record_id}").status_code == 404


def test_patch_record_updates_tags_notes_payload(client, default_member: dict) -> None:
    created = client.post(
        "/api/v1/records", json=make_record_body(default_member["id"])
    ).json()

    response = client.patch(
        f"/api/v1/records/{created['id']}",
        json={
            "tags": ["夜间"],
            "notes": "复查",
            "payload": {"k": 1},
            "metadata": {"resting": True},
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["tags"] == ["夜间"]
    assert updated["notes"] == "复查"
    assert updated["payload"] == {"k": 1}
    assert updated["metadata"] == {"resting": True}
    assert updated["id"] == created["id"]
    assert updated["createdAt"] == created["createdAt"]


def test_patch_record_rejects_invalid_values(client, default_member: dict) -> None:
    created = client.post(
        "/api/v1/records", json=make_record_body(default_member["id"])
    ).json()

    response = client.patch(f"/api/v1/records/{created['id']}", json={"notes": "x" * 4001})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"

    response = client.patch(f"/api/v1/records/{created['id']}", json={"signalIds": []})
    assert response.status_code == 422


def test_create_record_rejects_client_assigned_signal_ids(client, default_member: dict) -> None:
    body = make_record_body(
        default_member["id"],
        signalIds=["sig_00000000-0000-0000-0000-000000000000"],
    )
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "signal_ids_not_supported"


def test_signal_lead_must_be_listed(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"], leads=["II"])
    body["signal"] = {"lead": "I", "samples": [0.0, 1.0, 0.0]}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "lead_conflict"


def test_record_unknown_id(client) -> None:
    response = client.get("/api/v1/records/rec_00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["code"] == "record_not_found"

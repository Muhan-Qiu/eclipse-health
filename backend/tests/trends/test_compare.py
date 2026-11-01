"""记录对比 API：参数校验、最新完成分析、软删除（B3-02）。"""

from __future__ import annotations

from datetime import UTC, datetime

from trend_helpers import (
    add_completed_analysis,
    add_failed_analysis,
    add_running_analysis,
    create_record,
    measure,
)


def _get(client, ids: list[str]):
    return client.get("/api/v1/records/compare", params={"ids": ",".join(ids)})


def test_compare_returns_records_and_latest_completed(
    client, default_member: dict
) -> None:
    left = create_record(client, default_member["id"], captured_at="2026-10-28T08:00:00Z")
    right = create_record(client, default_member["id"], captured_at="2026-10-28T09:00:00Z")
    add_completed_analysis(
        left["id"],
        [measure("heart_rate_mean", 60.0, unit="bpm", ucum="/min")],
    )
    add_completed_analysis(
        right["id"],
        [measure("heart_rate_mean", 80.0, unit="bpm", ucum="/min")],
    )

    response = _get(client, [right["id"], left["id"]])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [record["id"] for record in body["records"]] == [right["id"], left["id"]]
    assert [entry["recordId"] for entry in body["analyses"]] == [right["id"], left["id"]]

    latest = body["analyses"][0]["latestCompleted"]
    assert latest["status"] == "completed"
    assert latest["measurements"][0]["code"] == "heart_rate_mean"
    assert latest["measurements"][0]["value"] == 80.0


def test_compare_uses_latest_completed_not_newer_failure(
    client, default_member: dict
) -> None:
    record = create_record(client, default_member["id"])
    other = create_record(client, default_member["id"])
    completed_id = add_completed_analysis(
        record["id"],
        [measure("heart_rate_mean", 66.0)],
        created_at=datetime(2026, 10, 28, 8, tzinfo=UTC),
    )
    add_failed_analysis(record["id"], created_at=datetime(2026, 10, 28, 9, tzinfo=UTC))
    add_running_analysis(record["id"], created_at=datetime(2026, 10, 28, 10, tzinfo=UTC))

    body = _get(client, [record["id"], other["id"]]).json()
    latest = body["analyses"][0]["latestCompleted"]
    assert latest["id"] == completed_id
    assert latest["measurements"][0]["value"] == 66.0
    assert body["analyses"][1]["latestCompleted"] is None


def test_compare_without_completed_analysis(client, default_member: dict) -> None:
    left = create_record(client, default_member["id"])
    right = create_record(client, default_member["id"])
    add_running_analysis(left["id"])

    body = _get(client, [left["id"], right["id"]]).json()
    assert body["analyses"][0]["latestCompleted"] is None
    assert body["analyses"][1]["latestCompleted"] is None


def test_compare_validates_id_count_and_duplicates(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])

    too_few = _get(client, [record["id"]])
    assert too_few.status_code == 422
    assert too_few.json()["code"] == "invalid_ids"

    too_many = _get(client, [record["id"]] + [f"rec_fake_{index}" for index in range(4)])
    assert too_many.status_code == 422
    assert too_many.json()["code"] == "invalid_ids"

    duplicate = _get(client, [record["id"], record["id"]])
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "invalid_ids"


def test_compare_unknown_or_deleted_record(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])

    missing = _get(client, [record["id"], "rec_00000000-0000-0000-0000-000000000000"])
    assert missing.status_code == 404
    assert missing.json()["code"] == "record_not_found"

    deleted = create_record(client, default_member["id"])
    assert client.delete(f"/api/v1/records/{deleted['id']}").status_code == 204
    response = _get(client, [record["id"], deleted["id"]])
    assert response.status_code == 404
    assert response.json()["code"] == "record_not_found"

"""记录列表的最新分析状态聚合（B3-02）。"""

from __future__ import annotations

from trend_helpers import (
    add_completed_analysis,
    add_failed_analysis,
    add_running_analysis,
    create_record,
    measure,
    utc,
)


def _items(client) -> dict[str, dict]:
    response = client.get("/api/v1/records", params={"limit": 50})
    assert response.status_code == 200, response.text
    page = response.json()
    assert set(page) == {"items", "total", "limit", "offset"}
    return {item["id"]: item for item in page["items"]}


def test_list_reports_latest_analysis_status(client, default_member: dict) -> None:
    member_id = default_member["id"]
    none_record = create_record(client, member_id, captured_at="2026-10-28T08:00:00Z")
    running_record = create_record(client, member_id, captured_at="2026-10-28T09:00:00Z")
    completed_record = create_record(client, member_id, captured_at="2026-10-28T10:00:00Z")
    failed_record = create_record(client, member_id, captured_at="2026-10-28T11:00:00Z")

    running_id = add_running_analysis(running_record["id"])
    completed_id = add_completed_analysis(
        completed_record["id"], [measure("heart_rate_mean", 72.0, unit="bpm", ucum="/min")]
    )
    failed_id = add_failed_analysis(failed_record["id"])

    items = _items(client)

    none_item = items[none_record["id"]]
    assert none_item["latestAnalysisStatus"] == "none"
    assert none_item["latestAnalysisId"] is None
    assert none_item["latestAnalyzedAt"] is None

    running_item = items[running_record["id"]]
    assert running_item["latestAnalysisStatus"] == "running"
    assert running_item["latestAnalysisId"] == running_id
    assert running_item["latestAnalyzedAt"] is None

    completed_item = items[completed_record["id"]]
    assert completed_item["latestAnalysisStatus"] == "completed"
    assert completed_item["latestAnalysisId"] == completed_id
    assert completed_item["latestAnalyzedAt"] is not None

    failed_item = items[failed_record["id"]]
    assert failed_item["latestAnalysisStatus"] == "failed"
    assert failed_item["latestAnalysisId"] == failed_id


def test_newest_analysis_wins(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(
        record["id"],
        [measure("heart_rate_mean", 60.0)],
        created_at=utc(2026, 10, 28, 8, 0, 0),
    )
    failed_id = add_failed_analysis(record["id"], created_at=utc(2026, 10, 28, 9, 0, 0))

    item = _items(client)[record["id"]]
    assert item["latestAnalysisStatus"] == "failed"
    assert item["latestAnalysisId"] == failed_id


def test_single_record_get_keeps_old_shape(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(record["id"], [measure("heart_rate_mean", 70.0)])

    response = client.get(f"/api/v1/records/{record['id']}")
    assert response.status_code == 200
    assert "latestAnalysisStatus" not in response.json()


def test_soft_deleted_records_are_excluded(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(record["id"], [measure("heart_rate_mean", 70.0)])

    assert client.delete(f"/api/v1/records/{record['id']}").status_code == 204
    assert _items(client) == {}


def test_pagination_keeps_status_fields(client, default_member: dict) -> None:
    member_id = default_member["id"]
    for hour in (8, 9, 10):
        record = create_record(
            client, member_id, captured_at=f"2026-10-28T{hour:02d}:00:00Z"
        )
        add_completed_analysis(record["id"], [measure("heart_rate_mean", 60.0 + hour)])

    page = client.get("/api/v1/records", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    for item in page["items"]:
        assert item["latestAnalysisStatus"] == "completed"
        assert item["latestAnalysisId"].startswith("ana_")

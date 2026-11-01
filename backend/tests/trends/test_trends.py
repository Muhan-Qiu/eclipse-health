"""趋势 API：过滤、排序、空数据、未知指标（B3-02）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from trend_helpers import add_completed_analysis, add_running_analysis, create_record, measure


def _series(response) -> dict[str, dict]:
    assert response.status_code == 200, response.text
    body = response.json()
    return {item["metric"]: item for item in body["series"]}


def test_default_metrics_and_ordering(client, default_member: dict) -> None:
    member_id = default_member["id"]
    late = create_record(client, member_id, captured_at="2026-10-28T10:00:00Z")
    early = create_record(client, member_id, captured_at="2026-10-28T08:00:00Z")
    add_completed_analysis(
        late["id"],
        [
            measure("heart_rate_mean", 80.0, unit="bpm", ucum="/min"),
            measure("rmssd", 40.0),
        ],
    )
    add_completed_analysis(
        early["id"],
        [
            measure("heart_rate_mean", 60.0, unit="bpm", ucum="/min"),
            measure("rmssd", 30.0),
        ],
    )

    series = _series(client.get("/api/v1/trends"))
    assert list(series) == ["heart_rate_mean", "rmssd"]

    hr = series["heart_rate_mean"]
    assert hr["unit"] == "bpm"
    assert hr["ucum"] == "/min"
    assert [point["value"] for point in hr["points"]] == [60.0, 80.0]
    assert [point["recordId"] for point in hr["points"]] == [early["id"], late["id"]]
    assert hr["points"][0]["t"].endswith("Z")
    assert hr["summary"] == {"min": 60.0, "max": 80.0, "mean": 70.0, "count": 2}


def test_explicit_metrics_and_dedupe(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(record["id"], [measure("sdnn", 45.0), measure("rmssd", 35.0)])

    series = _series(
        client.get("/api/v1/trends", params={"metrics": "sdnn,rmssd,sdnn"})
    )
    assert list(series) == ["sdnn", "rmssd"]


def test_unknown_metric_is_rejected(client) -> None:
    response = client.get("/api/v1/trends", params={"metrics": "heart_rate_mean,bogus"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unknown_metric"
    assert body["details"]["unknown"] == ["bogus"]
    assert "heart_rate_mean" in body["details"]["supported"]


def test_only_latest_completed_analysis_counts(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(
        record["id"],
        [measure("heart_rate_mean", 60.0)],
        created_at=datetime(2026, 10, 28, 8, tzinfo=UTC),
    )
    add_completed_analysis(
        record["id"],
        [measure("heart_rate_mean", 81.0)],
        created_at=datetime(2026, 10, 28, 9, tzinfo=UTC),
    )
    add_running_analysis(record["id"], created_at=datetime(2026, 10, 28, 10, tzinfo=UTC))

    hr = _series(client.get("/api/v1/trends"))["heart_rate_mean"]
    assert [point["value"] for point in hr["points"]] == [81.0]


def test_records_without_completed_analysis_are_skipped(
    client, default_member: dict
) -> None:
    record = create_record(client, default_member["id"])
    add_running_analysis(record["id"])

    hr = _series(client.get("/api/v1/trends"))["heart_rate_mean"]
    assert hr["points"] == []
    assert hr["summary"] == {"min": None, "max": None, "mean": None, "count": 0}


def test_null_values_are_skipped_not_zeroed(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(
        record["id"],
        [
            measure("heart_rate_mean", 72.0),
            measure("rmssd", None),
        ],
    )

    series = _series(client.get("/api/v1/trends"))
    assert len(series["heart_rate_mean"]["points"]) == 1
    assert series["rmssd"]["points"] == []
    assert series["rmssd"]["summary"]["count"] == 0


def test_from_to_filter_and_invalid_range(client, default_member: dict) -> None:
    member_id = default_member["id"]
    inside = create_record(client, member_id, captured_at="2026-10-20T08:00:00Z")
    outside = create_record(client, member_id, captured_at="2026-10-28T08:00:00Z")
    add_completed_analysis(inside["id"], [measure("heart_rate_mean", 61.0)])
    add_completed_analysis(outside["id"], [measure("heart_rate_mean", 62.0)])

    hr = _series(
        client.get(
            "/api/v1/trends",
            params={"from": "2026-10-19T00:00:00Z", "to": "2026-10-21T00:00:00Z"},
        )
    )["heart_rate_mean"]
    assert [point["recordId"] for point in hr["points"]] == [inside["id"]]

    bad = client.get(
        "/api/v1/trends",
        params={"from": "2026-10-28T00:00:00Z", "to": "2026-10-01T00:00:00Z"},
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_range"


def test_default_window_is_last_30_days(client, default_member: dict) -> None:
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat().replace("+00:00", "Z")
    recent = (datetime.now(UTC) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    old_record = create_record(client, default_member["id"], captured_at=old)
    recent_record = create_record(client, default_member["id"], captured_at=recent)
    add_completed_analysis(old_record["id"], [measure("heart_rate_mean", 50.0)])
    add_completed_analysis(recent_record["id"], [measure("heart_rate_mean", 70.0)])

    hr = _series(client.get("/api/v1/trends"))["heart_rate_mean"]
    assert [point["recordId"] for point in hr["points"]] == [recent_record["id"]]

    wide = _series(
        client.get(
            "/api/v1/trends",
            params={"from": (datetime.now(UTC) - timedelta(days=90)).isoformat()},
        )
    )["heart_rate_mean"]
    assert len(wide["points"]) == 2


def test_member_filter(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(record["id"], [measure("heart_rate_mean", 70.0)])

    matched = _series(
        client.get("/api/v1/trends", params={"memberId": default_member["id"]})
    )["heart_rate_mean"]
    assert len(matched["points"]) == 1

    unknown = _series(
        client.get("/api/v1/trends", params={"memberId": "mem_unknown"})
    )["heart_rate_mean"]
    assert unknown["points"] == []


def test_soft_deleted_records_are_excluded(client, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    add_completed_analysis(record["id"], [measure("heart_rate_mean", 70.0)])
    assert client.delete(f"/api/v1/records/{record['id']}").status_code == 204

    hr = _series(client.get("/api/v1/trends"))["heart_rate_mean"]
    assert hr["points"] == []


@pytest.mark.parametrize("metrics", ["", "   "])
def test_blank_metrics_fall_back_to_default(client, metrics: str) -> None:
    series = _series(client.get("/api/v1/trends", params={"metrics": metrics}))
    assert list(series) == ["heart_rate_mean", "rmssd"]

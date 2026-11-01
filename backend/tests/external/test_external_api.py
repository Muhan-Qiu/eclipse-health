"""外部 REST：记录/分析读取、聚合、健康数据写入与审计（F3）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from external_helpers import bearer, create_ecg_record, seed_analysis
from fastapi.testclient import TestClient
from sqlmodel import select

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.modules.audit import AuditEvent


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_records_are_summaries_without_sensitive_fields(
    client: TestClient, default_member: dict, write_key: dict
) -> None:
    headers = bearer(write_key["token"])
    record = create_ecg_record(
        client,
        default_member["id"],
        notes="这是不应外传的备注",
        tags=["晨起"],
    )
    created = client.post(
        "/api/v1/external/health-data",
        json={
            "kind": "steps",
            "value": 3210,
            "startAt": _iso(1),
            "endAt": _iso(1),
            "sourceApp": "test-app",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    listed = client.get("/api/v1/external/records", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert listed.headers["content-type"].startswith("application/json")
    assert "这是不应外传的备注" not in listed.text

    ecg = next(item for item in payload["items"] if item["id"] == record["id"])
    assert ecg["kind"] == "ecg"
    for forbidden in ("notes", "metadata", "tags", "payload", "signalIds"):
        assert forbidden not in ecg
    assert ecg["tagCount"] == 1
    assert ecg["leads"] == ["MLII"]

    health = next(item for item in payload["items"] if item["kind"] == "steps")
    assert health["value"] == 3210
    assert health["unit"] == "count"

    detail = client.get(f"/api/v1/external/records/{record['id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["payload"] is None
    assert body["record"]["id"] == record["id"]
    assert "notes" not in body["record"]

    health_detail = client.get(
        f"/api/v1/external/records/{health['id']}", headers=headers
    )
    assert health_detail.status_code == 200
    assert health_detail.json()["payload"]["value"] == 3210
    assert health_detail.json()["payload"]["unit"] == "count"


def test_analysis_returns_measurements_without_beats(
    client: TestClient, default_member: dict, read_key: dict
) -> None:
    headers = bearer(read_key["token"])
    record = create_ecg_record(client, default_member["id"])
    analysis_id = seed_analysis(record["id"], hr=68.0, rmssd=39.0)

    response = client.get(f"/api/v1/external/analyses/{analysis_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis"]["id"] == analysis_id
    assert body["analysis"]["status"] == "completed"
    assert "beats" not in body["analysis"]
    assert body["analysis"]["beatsTotal"] == 0
    codes = {item["code"] for item in body["measurements"]}
    assert {"heart_rate_mean", "rmssd", "sdnn"} <= codes
    assert '"beats":' not in response.text

    missing = client.get("/api/v1/external/analyses/ana_missing", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "analysis_not_found"


def test_health_data_write_validation_and_scope(
    client: TestClient, read_key: dict, write_key: dict
) -> None:
    read_headers = bearer(read_key["token"])
    write_headers = bearer(write_key["token"])

    denied = client.post(
        "/api/v1/external/health-data",
        json={"kind": "steps", "value": 1, "startAt": _iso()},
        headers=read_headers,
    )
    assert denied.status_code == 403

    steps = client.post(
        "/api/v1/external/health-data",
        json={"kind": "steps", "value": 8000, "startAt": _iso(1), "endAt": _iso(1)},
        headers=write_headers,
    )
    assert steps.status_code == 201, steps.text
    assert steps.json()["record"]["kind"] == "steps"

    sleep = client.post(
        "/api/v1/external/health-data",
        json={"kind": "sleep", "value": 420, "startAt": _iso(1), "endAt": _iso(0)},
        headers=write_headers,
    )
    assert sleep.status_code == 201, sleep.text

    pressure = client.post(
        "/api/v1/external/health-data",
        json={
            "kind": "blood-pressure",
            "value": {"systolic": 118, "diastolic": 76},
            "startAt": _iso(1),
        },
        headers=write_headers,
    )
    assert pressure.status_code == 201, pressure.text

    invalid = client.post(
        "/api/v1/external/health-data",
        json={
            "kind": "blood-pressure",
            "value": {"systolic": 10, "diastolic": 76},
            "startAt": _iso(),
        },
        headers=write_headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_blood_pressure"

    bad_range = client.post(
        "/api/v1/external/health-data",
        json={
            "kind": "steps",
            "value": 10,
            "startAt": _iso(),
            "endAt": _iso(2),
        },
        headers=write_headers,
    )
    assert bad_range.status_code == 422
    assert bad_range.json()["code"] == "invalid_time_range"

    listed = client.get("/api/v1/external/health-data?kind=steps", headers=write_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["value"] == 8000

    summary = client.get("/api/v1/external/summary?days=7", headers=write_headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["steps"]["latest"] == 8000
    assert body["sleep"]["latest"] == 420
    assert body["bloodPressure"]["latest"] == {"systolic": 118, "diastolic": 76}


def test_summary_empty_and_with_analysis(
    client: TestClient, default_member: dict, read_key: dict
) -> None:
    headers = bearer(read_key["token"])
    empty = client.get("/api/v1/external/summary", headers=headers)
    assert empty.status_code == 200
    body = empty.json()
    assert body["recordCount"] == 0
    assert body["analysisCount"] == 0
    for key in ("heartRate", "hrv", "quality", "steps", "sleep", "weight", "bloodPressure"):
        assert body[key] is None

    record = create_ecg_record(
        client,
        default_member["id"],
        quality={"score": 0.9, "level": "good", "warnings": [], "segments": []},
    )
    seed_analysis(record["id"], hr=64.0, rmssd=45.0)

    filled = client.get("/api/v1/external/summary?days=7", headers=headers).json()
    assert filled["recordCount"] == 1
    assert filled["analysisCount"] == 1
    assert filled["heartRate"]["latest"] == 64.0
    assert filled["hrv"]["latest"] == 45.0
    assert filled["quality"]["latest"] == 0.9
    assert filled["quality"]["level"] == "good"


def test_external_calls_are_audited(client: TestClient, read_key: dict) -> None:
    headers = bearer(read_key["token"])
    assert client.get("/api/v1/external/records", headers=headers).status_code == 200
    assert client.get("/api/v1/external/summary", headers=headers).status_code == 200

    with session_scope() as session:
        events = list(
            session.exec(
                select(AuditEvent)
                .where(AuditEvent.action == "external.call")
                .order_by(AuditEvent.created_at)
            )
        )
        details = [json.loads(event.detail_json or "{}") for event in events]
    actions = {detail.get("action") for detail in details}
    assert {"records.list", "summary.get"} <= actions
    record_event = next(detail for detail in details if detail["action"] == "records.list")
    assert record_event["keyId"] == read_key["id"]
    assert record_event["ok"] is True
    assert "error" not in record_event
    # 审计不包含任何健康数据内容字段。
    for detail in details:
        assert "data" not in detail
        assert "record" not in detail
        assert "summary" not in detail

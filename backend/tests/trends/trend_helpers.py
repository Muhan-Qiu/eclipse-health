"""趋势 / 对比测试的小工具：合成记录 + 直接写库的分析，不触发 ONNX。"""

from __future__ import annotations

from datetime import UTC, datetime

from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope

MODULE_ID = "org.eclipsehealth.cardia"


def create_record(
    client,
    member_id: str,
    *,
    captured_at: str = "2026-10-28T08:00:00Z",
    record_type: str = "org.eclipsehealth.ecg",
) -> dict:
    body = {
        "memberId": member_id,
        "recordType": record_type,
        "capturedAt": captured_at,
        "timezone": "Asia/Shanghai",
        "source": {"kind": "wearable", "manufacturer": "Synthetic"},
        "samplingRate": 500.0,
        "leads": ["I"],
        "unit": "mV",
        "tags": [],
        "notes": "",
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def measure(code: str, value: float | None, *, unit: str = "ms", ucum: str = "ms") -> dict:
    return {"code": code, "label": code, "value": value, "unit": unit, "ucum": ucum}


def add_completed_analysis(
    record_id: str,
    measurements: list[dict],
    *,
    created_at: datetime | None = None,
) -> str:
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id=MODULE_ID,
            model_id="cardia-2.0",
            model_version="2.0.0",
            created_at=created_at,
        )
        analysis_repo.save_result(
            session,
            row,
            {
                "status": "completed",
                "summary": "synthetic",
                "measurements": measurements,
                "beats": [],
            },
        )
        return row.id


def add_running_analysis(record_id: str, *, created_at: datetime | None = None) -> str:
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id=MODULE_ID,
            model_id="cardia-2.0",
            model_version="2.0.0",
            created_at=created_at,
        )
        analysis_repo.update_status(session, row, status="running")
        return row.id


def add_failed_analysis(record_id: str, *, created_at: datetime | None = None) -> str:
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id=MODULE_ID,
            model_id="cardia-2.0",
            model_version="2.0.0",
            created_at=created_at,
        )
        analysis_repo.save_failure(
            session, row, error={"code": "invalid_signal", "message": "synthetic"}
        )
        return row.id


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)

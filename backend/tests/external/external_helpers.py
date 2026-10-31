"""外部 API 测试的共用工具：合成记录、伪造已完成分析。"""

from __future__ import annotations

from typing import Any

from eclipse_health_backend.analysis.ids import rfc3339
from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.domain.common import utc_now

TEST_PROVIDER_ID = "llm_external_test"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ecg_record(
    client: Any,
    member_id: str,
    *,
    notes: str = "",
    tags: list[str] | None = None,
    captured_at: str = "2026-10-30T08:00:00Z",
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": captured_at,
        "timezone": "UTC",
        "source": {"kind": "file", "manufacturer": "Synthetic"},
        "samplingRate": 360.0,
        "leads": ["MLII"],
        "durationSec": 180.0,
        "unit": "mV",
        "tags": tags or [],
        "notes": notes,
    }
    if quality is not None:
        body["quality"] = quality
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def measurements(hr: float = 72.0, rmssd: float = 41.5) -> list[dict[str, Any]]:
    rows = [
        ("heart_rate_mean", "平均心率", hr, "bpm", "/min"),
        ("rmssd", "RMSSD", rmssd, "ms", "ms"),
        ("sdnn", "SDNN", 53.2, "ms", "ms"),
    ]
    return [
        {
            "schema": "org.eclipsehealth.measurement/1",
            "code": code,
            "label": label,
            "value": value,
            "unit": unit,
            "ucum": ucum,
            "range": {"startSec": 0, "endSec": 180},
            "confidence": 0.95,
            "method": "cardia-2.0",
            "warnings": [],
        }
        for code, label, value, unit, ucum in rows
    ]


def seed_analysis(
    record_id: str, *, hr: float = 72.0, rmssd: float = 41.5
) -> str:
    now = rfc3339(utc_now())
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id="org.eclipsehealth.cardia",
            model_id="cardia-2.0",
            model_version="2.0.0",
        )
        result = {
            "schema": "org.eclipsehealth.analysis/1",
            "id": row.id,
            "recordId": record_id,
            "moduleId": "org.eclipsehealth.cardia",
            "modelId": "cardia-2.0",
            "modelVersion": "2.0.0",
            "task": "beat-classification",
            "status": "completed",
            "startedAt": now,
            "completedAt": now,
            "durationMs": 12,
            "summary": f"平均心率 {hr:.0f} bpm",
            "quality": {"score": 0.93, "level": "good", "warnings": [], "segments": []},
            "measurements": measurements(hr, rmssd),
            "beats": [],
            "beatsRef": None,
            "annotations": [],
            "warnings": [],
            "parameters": {"engine": "cardia"},
            "provenance": {"preprocess": "cardia-v2"},
        }
        analysis_repo.save_result(session, row, result)
        return row.id

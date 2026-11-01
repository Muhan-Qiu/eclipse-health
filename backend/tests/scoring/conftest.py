"""G2 评分测试用的临时数据库夹具与记录构造器。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eclipse_health_backend.app import create_app
from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.repositories import add_record
from eclipse_health_backend.domain.common import utc_now
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.domain.models import HealthRecord, SourceInfo
from eclipse_health_backend.scoring.api import router

ECG_RECORD_TYPE = "org.eclipsehealth.ecg"


@pytest.fixture()
def api_client(client: TestClient) -> Iterator[TestClient]:
    """真实 app + 临时挂载 scoring router，模拟指挥官统一挂载后的路径。"""
    app = create_app()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as test_client:
        yield test_client


def add_health_record(
    member_id: str,
    record_type: str,
    captured_at: datetime,
    payload: dict[str, Any],
    *,
    duration_sec: float | None = None,
    metadata: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> str:
    now = utc_now()
    record = HealthRecord(
        id=new_id("record"),
        memberId=member_id,
        recordType=record_type,
        moduleId=None,
        capturedAt=captured_at,
        timezone="UTC",
        source=SourceInfo(kind="import"),
        samplingRate=None,
        leads=[],
        durationSec=duration_sec,
        unit="1",
        signalIds=[],
        tags=[],
        notes="",
        metadata=dict(metadata or {}),
        payload=payload,
        provenance=None,
        createdAt=now,
        updatedAt=now,
    )
    with session_scope() as session:
        add_record(session, record)
    return record.id


def add_ecg_analysis(
    member_id: str,
    captured_at: datetime,
    measurements: list[dict[str, Any]],
    *,
    quality: dict[str, Any] | None = None,
) -> str:
    record_id = add_health_record(member_id, ECG_RECORD_TYPE, captured_at, {})
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id="org.eclipsehealth.cardia",
            model_id="cardia-2.0",
            model_version="2.0.0",
            created_at=captured_at,
        )
        analysis_repo.save_result(
            session,
            row,
            {
                "status": "completed",
                "summary": "synthetic",
                "quality": quality,
                "measurements": measurements,
                "beats": [],
            },
        )
        return row.id


def measurement(code: str, value: float | None, unit: str = "ms") -> dict[str, Any]:
    return {"code": code, "label": code, "value": value, "unit": unit, "ucum": unit}


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


__all__ = [
    "ECG_RECORD_TYPE",
    "add_ecg_analysis",
    "add_health_record",
    "measurement",
    "utc",
]

"""OHS 同步：字段映射、去重、单条失败与空数据。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest
from sqlmodel import Session, select

from conftest import requires_dpapi
from eclipse_health_backend.db.models import RecordTable
from eclipse_health_backend.domain.errors import InvalidInputError
from eclipse_health_backend.ohs import store, sync
from eclipse_health_backend.ohs.client import OhsClient

pytestmark = requires_dpapi

BASE = "http://127.0.0.1:8080"
END = date(2026, 10, 30)


FULL_DAY = {
    "date": "2026-10-29",
    "steps": 8432,
    "restingHeartRate": 57,
    "sleepMinutes": 425,
    "weightKg": 70.25,
    "bloodPressure": {"systolic": 121, "diastolic": 79},
}


def _client(entries: list[dict[str, Any]], users: list[dict[str, Any]] | None = None) -> OhsClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/users":
            payload = {"users": users or [{"id": "u1", "name": "A"}]}
        elif request.url.path.endswith("/daily"):
            payload = {"daily": entries}
        else:  # pragma: no cover - 失败时给出可诊断信息
            return httpx.Response(404, json={"error": request.url.path})
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    return OhsClient(BASE, "tenant-secret", transport=httpx.MockTransport(handler))


def _rows(session: Session) -> list[RecordTable]:
    return list(session.exec(select(RecordTable).order_by(RecordTable.captured_at)))


def _by_type(session: Session) -> dict[str, list[RecordTable]]:
    grouped: dict[str, list[RecordTable]] = {}
    for row in _rows(session):
        grouped.setdefault(row.record_type, []).append(row)
    return grouped


def _member_id(session: Session) -> str:
    from eclipse_health_backend.db.repositories import ensure_default_member

    return ensure_default_member(session).id


def test_sync_maps_fields_and_dedupes(session: Session, clean_ohs: None) -> None:
    store.save_settings(BASE, "tenant-secret", "u1")
    second = dict(FULL_DAY, date="2026-10-30", steps=9100, restingHeartRate=60)

    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([FULL_DAY, second]),
        end_date=END,
    )

    assert (result.created, result.skipped, result.failed) == (10, 0, 0)
    assert result.warnings == []
    grouped = _by_type(session)
    assert len(grouped["org.eclipsehealth.health.steps"]) == 2
    assert len(grouped["org.eclipsehealth.health.heart-rate"]) == 2
    assert len(grouped["org.eclipsehealth.health.sleep"]) == 2
    assert len(grouped["org.eclipsehealth.health.body-mass"]) == 2
    assert len(grouped["org.eclipsehealth.health.blood-pressure"]) == 2

    steps = grouped["org.eclipsehealth.health.steps"][0]
    assert steps.payload["value"] == 8432
    assert steps.payload["unit"] == "count"
    assert steps.data["metadata"]["externalId"] == "ohs:u1:2026-10-29:steps"
    assert steps.data["metadata"]["importSource"] == "open-health-sync"
    assert steps.data["source"]["kind"] == "import"

    sleep = grouped["org.eclipsehealth.health.sleep"][0]
    assert sleep.payload["value"] == "asleep"
    assert sleep.data["durationSec"] == pytest.approx(425 * 60)

    pressure = grouped["org.eclipsehealth.health.blood-pressure"][0]
    assert pressure.payload["value"] == {"systolic": 121.0, "diastolic": 79.0}
    assert pressure.payload["unit"] == "mm[Hg]"

    again = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([FULL_DAY, second]),
        end_date=END,
    )
    assert (again.created, again.skipped, again.failed) == (0, 10, 0)
    assert len(_rows(session)) == 10


def test_unknown_fields_warn_without_guessing(session: Session, clean_ohs: None) -> None:
    store.save_settings(BASE, "tenant-secret", "u1")
    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([{"date": "2026-10-30", "mystery": 1}]),
        end_date=END,
    )
    assert result.created == 0
    assert result.warnings[0]["code"] == "ohs_unknown_daily_fields"
    assert _rows(session) == []


def test_incomplete_blood_pressure_warns_and_keeps_other_metrics(
    session: Session, clean_ohs: None
) -> None:
    store.save_settings(BASE, "tenant-secret", "u1")
    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([{"date": "2026-10-30", "steps": 100, "systolic": 120}]),
        end_date=END,
    )
    assert result.created == 1
    assert result.warnings[0]["code"] == "ohs_blood_pressure_incomplete"
    assert _rows(session)[0].record_type == "org.eclipsehealth.health.steps"


def test_single_failure_does_not_rollback_others(
    session: Session, clean_ohs: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.save_settings(BASE, "tenant-secret", "u1")
    original = sync.create_health_record

    def flaky(db_session: Session, draft: Any, **kwargs: Any) -> Any:
        if draft.kind == "steps":
            raise RuntimeError("simulated write failure")
        return original(db_session, draft, **kwargs)

    monkeypatch.setattr(sync, "create_health_record", flaky)
    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([FULL_DAY]),
        end_date=END,
    )
    assert (result.created, result.failed, result.skipped) == (4, 1, 0)
    assert any(item["code"] == "ohs_record_failed" for item in result.warnings)
    assert len(_rows(session)) == 4


def test_empty_daily_response_warns(session: Session, clean_ohs: None) -> None:
    store.save_settings(BASE, "tenant-secret", "u1")
    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client([]),
        end_date=END,
    )
    assert (result.created, result.failed) == (0, 0)
    assert result.warnings[0]["code"] == "ohs_no_daily_data"


def test_tenant_key_picks_first_user(session: Session, clean_ohs: None) -> None:
    store.save_settings(BASE, "tenant-secret", None)
    result = sync.sync_recent(
        session,
        _member_id(session),
        client=_client(
            [FULL_DAY],
            users=[{"id": "u1", "name": "A"}, {"id": "u2", "name": "B"}],
        ),
        end_date=END,
    )
    assert result.user_id == "u1"
    assert result.created == 5


def test_unconfigured_sync_rejected(session: Session, clean_ohs: None) -> None:
    with pytest.raises(InvalidInputError) as excinfo:
        sync.sync_recent(session, _member_id(session), end_date=END)
    assert excinfo.value.code == "ohs_not_configured"


def test_invalid_days_rejected(session: Session, clean_ohs: None) -> None:
    with pytest.raises(InvalidInputError) as excinfo:
        sync.sync_recent(session, _member_id(session), days=0, end_date=END)
    assert excinfo.value.code == "ohs_invalid_days"

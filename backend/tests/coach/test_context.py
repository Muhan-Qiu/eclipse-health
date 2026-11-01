"""教练上下文：健康摘要、运动记录、记忆开关、缺失模块容错。"""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta

from coach_helpers import seed_record

from eclipse_health_backend.coach import context as coach_context
from eclipse_health_backend.db.base import session_scope


def _context(member_id: str, **kwargs):
    with session_scope() as session:
        return coach_context.build_coach_context(session, member_id=member_id, **kwargs)


def test_empty_database_is_tolerated(client, default_member, monkeypatch) -> None:
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    payload = _context(default_member["id"])
    assert payload["health"] == {}
    assert payload["exercises"] == []
    assert payload["memory"] is None
    assert payload["weather"] is None
    assert payload["scores"] is None or payload["scores"]["overall"] is None


def test_health_summary_and_exercise(client, default_member, monkeypatch) -> None:
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    member_id = default_member["id"]
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)

    seed_record(
        member_id,
        "org.eclipsehealth.health.steps",
        {"value": 6000, "unit": "count", "startAt": now.isoformat()},
        captured_at=now,
    )
    seed_record(
        member_id,
        "org.eclipsehealth.health.steps",
        {"value": 4000, "unit": "count", "startAt": yesterday.isoformat()},
        captured_at=yesterday,
    )
    for value in (60, 70, 80):
        seed_record(
            member_id,
            "org.eclipsehealth.health.heart-rate",
            {"value": value, "unit": "count/min"},
            captured_at=now,
        )
    sleep_start = now - timedelta(hours=8)
    seed_record(
        member_id,
        "org.eclipsehealth.health.sleep",
        {
            "value": "asleep",
            "unit": "1",
            "startAt": sleep_start.isoformat(),
            "endAt": now.isoformat(),
        },
        captured_at=sleep_start,
        data={"metadata": {"sleepCategory": "asleep"}},
    )
    seed_record(
        member_id,
        "org.eclipsehealth.health.body-mass",
        {"value": 62.4, "unit": "kg"},
        captured_at=now,
    )
    seed_record(
        member_id,
        "org.eclipsehealth.health.blood-pressure",
        {"value": {"systolic": 118, "diastolic": 76}, "unit": "mm[Hg]"},
        captured_at=now,
    )
    seed_record(
        member_id,
        "org.eclipsehealth.health.exercise",
        {
            "activity": "walk",
            "durationSec": 1800,
            "distanceKm": 3.2,
            "intensity": "moderate",
            "subjective": "适中",
            "notes": "不应进入上下文",
            "startAt": now.isoformat(),
            "source": "manual",
        },
        captured_at=now,
    )

    payload = _context(member_id)
    health = payload["health"]
    assert health["steps"] == {
        "dailyAverage": 5000,
        "days": 2,
        "latest": 6000,
        "latestDate": now.date().isoformat(),
    }
    assert health["heartRate"]["average"] == 70.0
    assert health["heartRate"]["min"] == 60.0
    assert health["heartRate"]["max"] == 80.0
    assert health["sleep"]["averageHours"] == 8.0
    assert health["weight"]["value"] == 62.4
    assert health["bloodPressure"]["systolic"] == 118
    assert health["bloodPressure"]["diastolic"] == 76
    assert len(payload["exercises"]) == 1
    exercise = payload["exercises"][0]
    assert exercise["activity"] == "walk"
    assert exercise["durationSec"] == 1800
    assert "notes" not in exercise


def test_manual_metric_weight_and_pressure(client, default_member, monkeypatch) -> None:
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    member_id = default_member["id"]
    now = datetime.now(UTC)
    seed_record(
        member_id,
        "org.eclipsehealth.metric",
        {"kind": "weight", "values": {"weight": 70.2}},
        captured_at=now,
    )
    seed_record(
        member_id,
        "org.eclipsehealth.metric",
        {"kind": "blood_pressure", "values": {"systolic": 130, "diastolic": 85}},
        captured_at=now,
    )
    health = _context(member_id)["health"]
    assert health["weight"]["value"] == 70.2
    assert health["bloodPressure"]["systolic"] == 130


def test_broken_payload_is_skipped(client, default_member, monkeypatch) -> None:
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    member_id = default_member["id"]
    now = datetime.now(UTC)
    seed_record(
        member_id,
        "org.eclipsehealth.health.steps",
        {"value": "not-a-number"},
        captured_at=now,
    )
    seed_record(
        member_id,
        "org.eclipsehealth.health.exercise",
        {"activity": "run"},
        captured_at=now,
    )
    payload = _context(member_id)
    assert "steps" not in payload["health"]
    assert payload["exercises"] == []


def test_memory_enabled_and_disabled(monkeypatch) -> None:
    module = types.ModuleType("eclipse_health_backend.memory")
    module.memory_context = lambda: {"content": "喜欢晨跑，晚上十点后不吃东西", "enabled": True}
    monkeypatch.setitem(sys.modules, "eclipse_health_backend.memory", module)
    assert coach_context._memory_context() == {
        "content": "喜欢晨跑，晚上十点后不吃东西"
    }

    module.memory_context = lambda: {"content": "不应注入", "enabled": False}
    assert coach_context._memory_context() is None

    module.memory_context = lambda: ""
    assert coach_context._memory_context() is None


def test_real_memory_module_injection(client, default_member) -> None:
    from eclipse_health_backend.memory import MemoryUpdate, write_memory

    write_memory(MemoryUpdate(content="对花生过敏，偏好早上运动", enabled=True))
    try:
        payload = _context(default_member["id"])
        assert payload["memory"] == {"content": "对花生过敏，偏好早上运动"}
    finally:
        write_memory(MemoryUpdate(content="", enabled=False))


def test_real_memory_disabled_is_not_injected(client, default_member) -> None:
    from eclipse_health_backend.memory import MemoryUpdate, write_memory

    write_memory(MemoryUpdate(content="不应注入", enabled=False))
    payload = _context(default_member["id"])
    assert payload["memory"] is None


def test_missing_scoring_module_is_skipped(client, default_member, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "eclipse_health_backend.scoring.service", None)
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    payload = _context(default_member["id"])
    assert payload["scores"] is None


def test_weather_passed_through(client, default_member, monkeypatch) -> None:
    monkeypatch.setattr(coach_context, "_memory_context", lambda: None)
    weather = {"city": "上海", "days": [{"date": "2026-10-31", "tempMin": 14, "tempMax": 22}]}
    payload = _context(default_member["id"], weather=weather)
    assert payload["weather"] == weather

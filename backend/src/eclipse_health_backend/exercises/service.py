"""运动记录 <-> 核心记录的双向转换。"""

from __future__ import annotations

from typing import Any

from ..db.models import RecordTable
from ..db.repositories import record_from_row
from ..domain.models import HealthRecord, SourceInfo
from .models import EXERCISE_RECORD_TYPE, Exercise


def exercise_payload(
    *,
    activity: str,
    duration_sec: int,
    distance_km: float | None,
    intensity: str | None,
    subjective: str | None,
    notes: str,
    start_at: Any,
    source: str,
) -> dict[str, Any]:
    return {
        "activity": activity,
        "durationSec": duration_sec,
        "distanceKm": distance_km,
        "intensity": intensity,
        "subjective": subjective,
        "notes": notes,
        "startAt": start_at.isoformat(),
        "source": source,
    }


def build_exercise_record(
    *,
    record_id: str,
    member_id: str,
    activity: str,
    duration_sec: int,
    distance_km: float | None,
    intensity: str | None,
    subjective: str | None,
    notes: str,
    start_at: Any,
    source: str,
    timezone: str,
    created_at: Any,
    updated_at: Any,
) -> HealthRecord:
    return HealthRecord(
        id=record_id,
        memberId=member_id,
        recordType=EXERCISE_RECORD_TYPE,
        moduleId=None,
        capturedAt=start_at,
        timezone=timezone,
        source=SourceInfo(kind=source),
        samplingRate=None,
        leads=[],
        durationSec=None,
        signalIds=[],
        quality=None,
        tags=[],
        notes=notes,
        metadata={},
        payload=exercise_payload(
            activity=activity,
            duration_sec=duration_sec,
            distance_km=distance_km,
            intensity=intensity,
            subjective=subjective,
            notes=notes,
            start_at=start_at,
            source=source,
        ),
        provenance=None,
        createdAt=created_at,
        updatedAt=updated_at,
        deletedAt=None,
    )


def exercise_from_row(row: RecordTable) -> Exercise | None:
    """payload 损坏时返回 ``None``，避免一条坏数据拖垮列表。"""
    payload = row.payload or {}
    try:
        record = record_from_row(row)
        return Exercise(
            id=record.id,
            memberId=record.memberId,
            activity=payload["activity"],
            durationSec=payload["durationSec"],
            distanceKm=payload.get("distanceKm"),
            intensity=payload.get("intensity"),
            subjective=payload.get("subjective"),
            notes=payload.get("notes") or record.notes,
            startAt=payload["startAt"],
            source=payload.get("source", "manual"),
            createdAt=record.createdAt,
            updatedAt=record.updatedAt,
        )
    except (KeyError, TypeError, ValueError):
        return None


__all__ = ["build_exercise_record", "exercise_from_row", "exercise_payload"]

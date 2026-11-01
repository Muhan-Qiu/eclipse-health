"""指标 <-> 记录的双向转换。"""

from __future__ import annotations

from typing import Any

from ..db.models import RecordTable
from ..db.repositories import record_from_row
from ..domain.models import HealthRecord, SourceInfo
from .models import (
    METRIC_RECORD_TYPE,
    UNIT_BY_KIND,
    Metric,
    MetricKind,
    compute_warnings,
    normalize_values,
)


def build_metric_record(
    *,
    record_id: str,
    member_id: str,
    kind: MetricKind,
    measured_at: Any,
    timezone: str,
    values: dict[str, float],
    notes: str,
    tags: list[str],
    created_at: Any,
    updated_at: Any,
) -> HealthRecord:
    return HealthRecord(
        id=record_id,
        memberId=member_id,
        recordType=METRIC_RECORD_TYPE,
        moduleId=None,
        capturedAt=measured_at,
        timezone=timezone,
        source=SourceInfo(kind="manual"),
        samplingRate=None,
        leads=[],
        durationSec=None,
        unit=UNIT_BY_KIND[kind.value],
        signalIds=[],
        quality=None,
        tags=tags,
        notes=notes,
        metadata={},
        payload={"kind": kind.value, "values": values},
        provenance=None,
        createdAt=created_at,
        updatedAt=updated_at,
        deletedAt=None,
    )


def metric_from_row(row: RecordTable) -> Metric | None:
    """无法解析的 payload 返回 ``None``，避免一条坏数据拖垮整个列表。"""
    payload = row.payload or {}
    kind_raw = payload.get("kind")
    values_raw = payload.get("values")
    try:
        kind = MetricKind(kind_raw)
        if not isinstance(values_raw, dict):
            return None
        values = normalize_values(kind, values_raw)
    except (ValueError, TypeError):
        return None

    record = record_from_row(row)
    return Metric(
        id=record.id,
        memberId=record.memberId,
        kind=kind,
        measuredAt=record.capturedAt,
        timezone=record.timezone,
        values=values,
        unit=UNIT_BY_KIND[kind.value],
        notes=record.notes,
        tags=list(record.tags),
        warnings=compute_warnings(kind, values),
        createdAt=record.createdAt,
        updatedAt=record.updatedAt,
    )


def metric_payload(kind: MetricKind, values: dict[str, float]) -> dict[str, Any]:
    return {"kind": kind.value, "values": values}


__all__ = ["build_metric_record", "metric_from_row", "metric_payload"]

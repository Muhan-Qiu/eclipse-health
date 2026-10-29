"""趋势序列组装：一条聚合查询取「每条记录最新一次完成分析」的指定测量值。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from ..analysis.ids import rfc3339
from ..db.models import AnalysisTable, MeasurementTable, RecordTable
from .metrics import METRIC_CATALOG


def _latest_completed_subquery():
    """每条记录最新一条 completed 分析（窗口函数，避免逐记录再查）。"""
    rank = func.row_number().over(
        partition_by=AnalysisTable.record_id,
        order_by=(AnalysisTable.created_at.desc(), AnalysisTable.id.desc()),
    )
    return (
        select(
            AnalysisTable.record_id.label("record_id"),
            AnalysisTable.id.label("analysis_id"),
            rank.label("rn"),
        )
        .where(AnalysisTable.status == "completed")
        .subquery()
    )


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return {
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "mean": round(sum(values) / len(values), 2),
        "count": len(values),
    }


def build_trends(
    session: Session,
    *,
    metrics: list[str],
    since: datetime | None,
    until: datetime | None,
    member_id: str | None,
) -> list[dict[str, Any]]:
    latest = _latest_completed_subquery()
    statement = (
        select(
            MeasurementTable.code,
            MeasurementTable.value,
            RecordTable.id.label("record_id"),
            RecordTable.captured_at,
            latest.c.analysis_id,
        )
        .join(latest, MeasurementTable.analysis_id == latest.c.analysis_id)
        .join(RecordTable, RecordTable.id == MeasurementTable.record_id)
        .where(
            latest.c.rn == 1,
            RecordTable.deleted_at.is_(None),
            MeasurementTable.code.in_(metrics),
            MeasurementTable.value.is_not(None),
        )
        .order_by(RecordTable.captured_at.asc(), RecordTable.id.asc())
    )
    if member_id:
        statement = statement.where(RecordTable.member_id == member_id)
    if since is not None:
        statement = statement.where(RecordTable.captured_at >= since)
    if until is not None:
        statement = statement.where(RecordTable.captured_at <= until)

    buckets: dict[str, list[dict[str, Any]]] = {code: [] for code in metrics}
    for row in session.execute(statement).all():
        value = row.value
        if value is None:
            continue
        buckets[row.code].append(
            {
                "t": rfc3339(row.captured_at),
                "value": float(value),
                "recordId": row.record_id,
                "analysisId": row.analysis_id,
            }
        )

    series: list[dict[str, Any]] = []
    for code in metrics:
        meta = METRIC_CATALOG[code]
        points = buckets[code]
        series.append(
            {
                "metric": meta.code,
                "label": meta.label,
                "unit": meta.unit,
                "ucum": meta.ucum,
                "points": points,
                "summary": _summary([point["value"] for point in points]),
            }
        )
    return series


__all__ = ["build_trends"]

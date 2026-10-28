"""分析结果持久化：``analyses`` / ``measurements`` / ``annotations``（Schema §11）。

只做单对象读写，查询与分页留在 API 层；``data`` 列存完整 AnalysisResult
（含 beats 内联，≤50k，Schema §12）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from ..domain.common import to_storage_dt, utc_now
from ..domain.ids import new_id
from .models import AnalysisTable, AnnotationTable, MeasurementTable

SCHEMA_ANALYSIS = "org.eclipsehealth.analysis/1"

ACTIVE_STATUSES = ("queued", "running")
FINAL_STATUSES = ("completed", "failed", "cancelled")

# 分析摘要字段：列表接口不返回 beats / measurements，避免大记录放大响应。
SUMMARY_FIELDS = (
    "id",
    "recordId",
    "engine",
    "moduleId",
    "modelId",
    "modelVersion",
    "task",
    "status",
    "summary",
    "quality",
    "createdAt",
    "startedAt",
    "completedAt",
    "durationMs",
    "progress",
    "error",
    "warnings",
    "parameters",
    "provenance",
)


def new_analysis_id() -> str:
    return new_id("analysis")


def build_analysis_data(
    *,
    analysis_id: str,
    record_id: str,
    engine: str,
    module_id: str,
    model_id: str,
    model_version: str,
    created_at: datetime,
) -> dict[str, Any]:
    """发起分析时的空结果骨架；引擎返回后由 ``merge_result`` 覆盖。"""
    return {
        "schema": SCHEMA_ANALYSIS,
        "id": analysis_id,
        "recordId": record_id,
        "engine": engine,
        "moduleId": module_id,
        "modelId": model_id,
        "modelVersion": model_version,
        "task": "beat-classification",
        "status": "queued",
        "createdAt": _iso(created_at),
        "startedAt": None,
        "completedAt": None,
        "durationMs": None,
        "summary": None,
        "quality": None,
        "measurements": [],
        "beats": [],
        "beatsRef": None,
        "annotations": [],
        "warnings": [],
        "parameters": {"engine": engine},
        "provenance": {},
        "progress": None,
        "error": None,
    }


def _iso(value: datetime) -> str:
    from ..analysis.ids import rfc3339

    return rfc3339(value)


def create_analysis(
    session: Session,
    *,
    record_id: str,
    engine: str,
    module_id: str,
    model_id: str,
    model_version: str,
    analysis_id: str | None = None,
    created_at: datetime | None = None,
) -> AnalysisTable:
    analysis_id = analysis_id or new_analysis_id()
    created_at = created_at or utc_now()
    data = build_analysis_data(
        analysis_id=analysis_id,
        record_id=record_id,
        engine=engine,
        module_id=module_id,
        model_id=model_id,
        model_version=model_version,
        created_at=created_at,
    )
    row = AnalysisTable(
        id=analysis_id,
        record_id=record_id,
        module_id=module_id,
        model_id=model_id,
        status="queued",
        data=data,
        created_at=to_storage_dt(created_at),
    )
    session.add(row)
    session.commit()
    return row


def get_analysis_row(session: Session, analysis_id: str) -> AnalysisTable | None:
    return session.get(AnalysisTable, analysis_id)


def list_analysis_rows(
    session: Session, record_id: str, *, limit: int = 50, offset: int = 0
) -> list[AnalysisTable]:
    statement = (
        select(AnalysisTable)
        .where(AnalysisTable.record_id == record_id)
        .order_by(AnalysisTable.created_at.desc(), AnalysisTable.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(statement))


def find_active_row(session: Session, record_id: str) -> AnalysisTable | None:
    statement = (
        select(AnalysisTable)
        .where(
            AnalysisTable.record_id == record_id,
            AnalysisTable.status.in_(ACTIVE_STATUSES),
        )
        .order_by(AnalysisTable.created_at.desc())
    )
    return session.exec(statement).first()


def latest_row(session: Session, record_id: str) -> AnalysisTable | None:
    statement = (
        select(AnalysisTable)
        .where(AnalysisTable.record_id == record_id)
        .order_by(AnalysisTable.created_at.desc())
    )
    return session.exec(statement).first()


def update_status(
    session: Session,
    row: AnalysisTable,
    *,
    status: str,
    progress: dict[str, Any] | None | object = ...,
    error: dict[str, Any] | None | object = ...,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    commit: bool = True,
) -> AnalysisTable:
    """推进状态机；只在内存里改 ``data``，调用方负责提交。"""
    data = dict(row.data)
    data["status"] = status
    if progress is not ...:
        data["progress"] = progress
    if error is not ...:
        data["error"] = error
    if started_at is not None:
        data["startedAt"] = _iso(started_at)
    if completed_at is not None:
        data["completedAt"] = _iso(completed_at)
    row.data = data
    row.status = status
    session.add(row)
    if commit:
        session.commit()
    return row


def save_result(session: Session, row: AnalysisTable, result: dict[str, Any]) -> AnalysisTable:
    """把引擎结果落库：analyses.data + measurements + annotations。"""
    data = dict(result) if isinstance(result, dict) else {}
    data["id"] = row.id
    data["recordId"] = row.record_id
    data["status"] = "completed"
    data.setdefault("engine", (row.data or {}).get("engine", "cardia"))
    data["createdAt"] = (row.data or {}).get("createdAt")
    data["progress"] = {"stage": "summary", "percent": 100}
    data["error"] = None
    beats = data.get("beats") or []
    if len(beats) > 50_000:
        # Schema §12：内联上限 50k；B2 不做 beatsRef 文件，明确截断而不是悄悄放大 JSON。
        data["beats"] = beats[:50_000]
        warnings = list(data.get("warnings") or [])
        warnings.append(
            {
                "code": "beats_truncated",
                "severity": "warning",
                "message": f"逐搏结果超过 50000 条，已截断 {len(beats) - 50_000} 条",
                "startSec": None,
                "endSec": None,
            }
        )
        data["warnings"] = warnings

    row.data = data
    row.status = "completed"
    row.module_id = data.get("moduleId") or row.module_id
    row.model_id = data.get("modelId") or row.model_id
    session.add(row)

    _replace_measurements(session, row, data.get("measurements") or [])
    _replace_annotations(session, row, data.get("annotations") or [])
    session.commit()
    return row


def _replace_measurements(session: Session, row: AnalysisTable, items: list[Any]) -> None:
    for existing in session.exec(
        select(MeasurementTable).where(MeasurementTable.analysis_id == row.id)
    ):
        session.delete(existing)
    for item in items:
        if not isinstance(item, dict):
            continue
        measurement_id = item.get("id") or new_id("measurement")
        payload = dict(item)
        payload["id"] = measurement_id
        payload.setdefault("analysisId", row.id)
        payload.setdefault("recordId", row.record_id)
        session.add(
            MeasurementTable(
                id=measurement_id,
                record_id=row.record_id,
                analysis_id=row.id,
                code=str(payload.get("code") or "unknown"),
                value=payload.get("value"),
                unit=payload.get("unit"),
                data=payload,
                created_at=utc_now(),
            )
        )


def _replace_annotations(session: Session, row: AnalysisTable, items: list[Any]) -> None:
    for existing in session.exec(
        select(AnnotationTable).where(AnnotationTable.analysis_id == row.id)
    ):
        session.delete(existing)
    for item in items:
        if not isinstance(item, dict):
            continue
        annotation_id = item.get("id") or new_id("annotation")
        payload = dict(item)
        payload["id"] = annotation_id
        payload.setdefault("analysisId", row.id)
        payload.setdefault("recordId", row.record_id)
        session.add(
            AnnotationTable(
                id=annotation_id,
                record_id=row.record_id,
                analysis_id=row.id,
                type=str(payload.get("type") or "event"),
                label=payload.get("label"),
                data=payload,
                created_at=utc_now(),
            )
        )


def save_failure(
    session: Session,
    row: AnalysisTable,
    *,
    error: dict[str, Any],
    warnings: list[dict[str, Any]] | None = None,
    completed_at: datetime | None = None,
) -> AnalysisTable:
    row = update_status(
        session,
        row,
        status="failed",
        progress=None,
        error=error,
        completed_at=completed_at or utc_now(),
        commit=False,
    )
    if warnings is not None:
        data = dict(row.data)
        data["warnings"] = warnings
        row.data = data
        session.add(row)
    session.commit()
    return row


def measurements_for(session: Session, analysis_id: str) -> list[dict[str, Any]]:
    statement = (
        select(MeasurementTable)
        .where(MeasurementTable.analysis_id == analysis_id)
        .order_by(MeasurementTable.code)
    )
    return [row.data for row in session.exec(statement)]


def annotations_for(session: Session, analysis_id: str) -> list[dict[str, Any]]:
    statement = (
        select(AnnotationTable)
        .where(AnnotationTable.analysis_id == analysis_id)
        .order_by(AnnotationTable.created_at, AnnotationTable.id)
    )
    return [row.data for row in session.exec(statement)]


def summary_of(row: AnalysisTable) -> dict[str, Any]:
    data = row.data or {}
    summary = {field: data.get(field) for field in SUMMARY_FIELDS}
    summary["id"] = row.id
    summary["recordId"] = row.record_id
    summary["status"] = row.status
    summary["engine"] = data.get("engine") or "cardia"
    summary["createdAt"] = data.get("createdAt") or _iso(row.created_at)
    # 列表不返回 beats 本体，但给出总数，UI 无需再拉详情即可判断「有没有逐搏」。
    summary["beatsTotal"] = len(data.get("beats") or [])
    return summary


def detail_of(
    session: Session, row: AnalysisTable, *, include_beats: bool = True
) -> dict[str, Any]:
    data = dict(row.data or {})
    detail = summary_of(row)
    measurements = data.get("measurements")
    if not measurements:
        measurements = measurements_for(session, row.id)
    detail["measurements"] = measurements
    beats = data.get("beats") or []
    detail["beatsTotal"] = len(beats)
    detail["beats"] = beats if include_beats else None
    detail["beatsRef"] = data.get("beatsRef")
    detail["parameters"] = data.get("parameters") or {}
    detail["provenance"] = data.get("provenance") or {}
    detail["quality"] = data.get("quality")
    detail["warnings"] = data.get("warnings") or []
    detail["annotations"] = data.get("annotations") or []
    return detail


def beats_page(
    session: Session, row: AnalysisTable, *, offset: int, limit: int
) -> dict[str, Any]:
    beats = (row.data or {}).get("beats") or []
    total = len(beats)
    return {
        "items": beats[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


__all__ = [
    "ACTIVE_STATUSES",
    "FINAL_STATUSES",
    "annotations_for",
    "beats_page",
    "build_analysis_data",
    "create_analysis",
    "detail_of",
    "find_active_row",
    "get_analysis_row",
    "latest_row",
    "list_analysis_rows",
    "measurements_for",
    "new_analysis_id",
    "save_failure",
    "save_result",
    "summary_of",
    "update_status",
]

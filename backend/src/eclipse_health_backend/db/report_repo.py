"""报告元数据持久化：复用 ``reports`` 表（Schema §9 / §11）。

表里只存可检索列（id/recordId/analysisId/format/createdAt），完整对象放 ``data``；
文件本体在 ``data/reports/<id>.<ext>``，由 ``storage.files`` 原子写入并校验 sha256。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from ..analysis.ids import rfc3339
from ..db.models import AnalysisTable, ReportTable
from ..domain.common import to_storage_dt, utc_now

SCHEMA_REPORT = "org.eclipsehealth.report/1"


def build_report_data(
    *,
    report_id: str,
    record_id: str,
    analysis_id: str,
    format: str,
    template: str,
    relative_path: str,
    sha256: str,
    size: int,
    redacted: bool,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_REPORT,
        "id": report_id,
        "recordId": record_id,
        "analysisId": analysis_id,
        "templateId": template,
        "format": format,
        "redacted": redacted,
        "storage": {"relativePath": relative_path, "sha256": sha256, "size": int(size)},
        "createdAt": rfc3339(created_at),
    }


def create_report_row(
    session: Session,
    *,
    report_id: str,
    record_id: str,
    analysis_id: str,
    format: str,
    template: str,
    relative_path: str,
    sha256: str,
    size: int,
    redacted: bool,
    created_at: datetime | None = None,
) -> ReportTable:
    created_at = created_at or utc_now()
    row = ReportTable(
        id=report_id,
        record_id=record_id,
        analysis_id=analysis_id,
        format=format,
        data=build_report_data(
            report_id=report_id,
            record_id=record_id,
            analysis_id=analysis_id,
            format=format,
            template=template,
            relative_path=relative_path,
            sha256=sha256,
            size=size,
            redacted=redacted,
            created_at=created_at,
        ),
        created_at=to_storage_dt(created_at),
    )
    session.add(row)
    session.commit()
    return row


def get_report_row(session: Session, report_id: str) -> ReportTable | None:
    return session.get(ReportTable, report_id)


def list_report_rows(
    session: Session, record_id: str, *, limit: int = 100, offset: int = 0
) -> list[ReportTable]:
    statement = (
        select(ReportTable)
        .where(ReportTable.record_id == record_id)
        .order_by(ReportTable.created_at.desc(), ReportTable.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(statement))


def count_report_rows(session: Session, record_id: str) -> int:
    from sqlalchemy import func

    statement = (
        select(func.count())
        .select_from(ReportTable)
        .where(ReportTable.record_id == record_id)
    )
    return int(session.exec(statement).one())


def delete_report_row(session: Session, row: ReportTable) -> None:
    session.delete(row)
    session.commit()


def latest_completed_analysis_row(session: Session, record_id: str) -> AnalysisTable | None:
    statement = (
        select(AnalysisTable)
        .where(
            AnalysisTable.record_id == record_id,
            AnalysisTable.status == "completed",
        )
        .order_by(AnalysisTable.created_at.desc(), AnalysisTable.id.desc())
    )
    return session.exec(statement).first()


def storage_of(row: ReportTable) -> dict[str, Any]:
    data = row.data or {}
    storage = data.get("storage")
    return storage if isinstance(storage, dict) else {}


def template_of(row: ReportTable) -> str:
    data = row.data or {}
    return str(data.get("templateId") or "detailed")


def redacted_of(row: ReportTable) -> bool:
    data = row.data or {}
    return bool(data.get("redacted", True))


def file_name_of(row: ReportTable) -> str:
    """下载文件名不含成员/记录信息，只保留日期与报告短 ID。"""
    created = str((row.data or {}).get("createdAt") or "")
    date_part = created[:10].replace("-", "") or "report"
    short = row.id.split("_")[-1].replace("-", "")[:8]
    return f"eclipse-health-report-{date_part}-{short}.{row.format}"


def summary_of(row: ReportTable) -> dict[str, Any]:
    storage = storage_of(row)
    created_at = (row.data or {}).get("createdAt") or rfc3339(row.created_at)
    return {
        "reportId": row.id,
        "recordId": row.record_id,
        "analysisId": row.analysis_id,
        "format": row.format,
        "template": template_of(row),
        "fileName": file_name_of(row),
        "size": int(storage.get("size") or 0),
        "sha256": str(storage.get("sha256") or ""),
        "redacted": redacted_of(row),
        "createdAt": created_at,
        "downloadUrl": f"/api/v1/reports/{row.id}/download",
    }


__all__ = [
    "SCHEMA_REPORT",
    "count_report_rows",
    "create_report_row",
    "delete_report_row",
    "file_name_of",
    "get_report_row",
    "latest_completed_analysis_row",
    "list_report_rows",
    "redacted_of",
    "storage_of",
    "summary_of",
    "template_of",
]

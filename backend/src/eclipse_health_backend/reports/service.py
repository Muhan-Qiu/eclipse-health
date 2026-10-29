"""报告服务：校验 → 组装内容 → 渲染 → 原子写文件 → 落库。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session

from ..db import report_repo
from ..db.repositories import get_record_row
from ..domain.common import utc_now
from ..domain.errors import ConflictError, InvalidInputError, not_found
from ..domain.ids import new_id
from ..settings import get_settings
from ..storage.files import read_report, write_report
from .content import build_report_content

PDF_TEMPLATES = ("simple", "detailed", "doctor")
REPORT_FORMATS = ("pdf", "png")

CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png"}


def create_report(
    session: Session,
    record_id: str,
    *,
    format: str = "pdf",
    template: str = "detailed",
    redact: bool = True,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if format not in REPORT_FORMATS:
        raise InvalidInputError(
            "unsupported report format",
            code="unsupported_format",
            details={"format": format, "allowed": list(REPORT_FORMATS)},
        )
    if template not in PDF_TEMPLATES:
        raise InvalidInputError(
            "unknown report template",
            code="unknown_template",
            details={"template": template, "allowed": list(PDF_TEMPLATES)},
        )

    record_row = get_record_row(session, record_id)
    if record_row is None or record_row.deleted_at is not None:
        raise not_found("record", record_id)

    analysis_row = report_repo.latest_completed_analysis_row(session, record_id)
    if analysis_row is None:
        raise ConflictError(
            "a completed analysis is required before generating a report",
            code="analysis_required",
            details={"recordId": record_id},
        )

    report_id = new_id("report")
    generated_at = created_at or utc_now()
    content = build_report_content(
        session,
        record_row,
        analysis_row,
        template=template,
        redact=redact,
        report_id=report_id,
        generated_at=generated_at,
    )
    # 延迟导入：matplotlib 体积与内存都不应计入后端启动路径。
    if format == "pdf":
        from .pdf import render_pdf

        data = render_pdf(content)
    else:
        from .share_card import render_share_card

        data = render_share_card(content)

    relative_path, sha256, size = write_report(report_id, format, data)
    try:
        row = report_repo.create_report_row(
            session,
            report_id=report_id,
            record_id=record_id,
            analysis_id=analysis_row.id,
            format=format,
            template=template,
            relative_path=relative_path,
            sha256=sha256,
            size=size,
            redacted=redact,
            created_at=generated_at,
        )
    except Exception:
        _unlink_report_file(report_id, format)
        raise
    return report_repo.summary_of(row)


def list_reports(
    session: Session, record_id: str, *, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    record_row = get_record_row(session, record_id)
    if record_row is None or record_row.deleted_at is not None:
        raise not_found("record", record_id)
    rows = report_repo.list_report_rows(session, record_id, limit=limit, offset=offset)
    return {
        "items": [report_repo.summary_of(row) for row in rows],
        "total": report_repo.count_report_rows(session, record_id),
        "limit": limit,
        "offset": offset,
    }


def get_report(session: Session, report_id: str) -> dict[str, Any]:
    row = report_repo.get_report_row(session, report_id)
    if row is None:
        raise not_found("report", report_id)
    return report_repo.summary_of(row)


def read_report_file(session: Session, report_id: str) -> tuple[bytes, dict[str, Any]]:
    row = report_repo.get_report_row(session, report_id)
    if row is None:
        raise not_found("report", report_id)
    storage = report_repo.storage_of(row)
    relative_path = str(storage.get("relativePath") or "")
    sha256 = str(storage.get("sha256") or "")
    data = read_report(relative_path, sha256)
    return data, report_repo.summary_of(row)


def delete_report(session: Session, report_id: str) -> None:
    row = report_repo.get_report_row(session, report_id)
    if row is None:
        raise not_found("report", report_id)
    _unlink_report_file(row.id, row.format)
    report_repo.delete_report_row(session, row)


def _unlink_report_file(report_id: str, format: str) -> None:
    if format not in REPORT_FORMATS:
        return
    path = Path(get_settings().reports_dir) / f"{report_id}.{format}"
    path.unlink(missing_ok=True)


__all__ = [
    "CONTENT_TYPES",
    "PDF_TEMPLATES",
    "REPORT_FORMATS",
    "create_report",
    "delete_report",
    "get_report",
    "list_reports",
    "read_report_file",
]

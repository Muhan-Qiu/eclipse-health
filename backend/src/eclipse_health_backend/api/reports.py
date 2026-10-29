"""报告 API：生成、历史、元数据、下载、删除。

- 生成前必须有 ``completed`` 分析，否则 409 ``analysis_required``；
- 未知格式/模板由 Pydantic ``Literal`` 与 service 双重校验，返回 422；
- 下载时重新校验 sha256，Content-Type/Disposition 按格式给出；
- 文件名由服务端生成，不含成员、备注或原始文件名。
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from ..reports.service import (
    CONTENT_TYPES,
    create_report,
    delete_report,
    get_report,
    list_reports,
    read_report_file,
)
from .deps import SessionDep

router = APIRouter(tags=["reports"])

ReportFormat = Literal["pdf", "png"]
ReportTemplate = Literal["simple", "detailed", "doctor"]


class ReportCreate(BaseModel):
    format: ReportFormat = Field(default="pdf", description="pdf 或 png 分享卡")
    template: ReportTemplate = Field(default="detailed", description="PDF 模板")
    redact: bool = Field(default=True, description="脱敏：不显示成员姓名、备注与原始文件名")


class ReportSummary(BaseModel):
    reportId: str
    recordId: str
    analysisId: str | None = None
    format: str
    template: str
    fileName: str
    size: int
    sha256: str
    redacted: bool
    createdAt: str | None = None
    downloadUrl: str


class ReportList(BaseModel):
    items: list[ReportSummary]
    total: int
    limit: int
    offset: int


@router.post(
    "/records/{record_id}/reports",
    response_model=ReportSummary,
    status_code=status.HTTP_201_CREATED,
    summary="生成 PDF / PNG 报告",
    responses={409: {"description": "记录尚无已完成分析（analysis_required）"}},
)
def generate_report(
    record_id: str, payload: ReportCreate, session: SessionDep
) -> ReportSummary:
    summary = create_report(
        session,
        record_id,
        format=payload.format,
        template=payload.template,
        redact=payload.redact,
    )
    return ReportSummary.model_validate(summary)


@router.get(
    "/records/{record_id}/reports",
    response_model=ReportList,
    summary="列出某条记录的报告历史",
)
def history(
    record_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportList:
    body = list_reports(session, record_id, limit=limit, offset=offset)
    return ReportList.model_validate(body)


@router.get("/reports/{report_id}", response_model=ReportSummary, summary="读取报告元数据")
def metadata(report_id: str, session: SessionDep) -> ReportSummary:
    return ReportSummary.model_validate(get_report(session, report_id))


@router.get(
    "/reports/{report_id}/download",
    summary="下载报告文件",
    responses={200: {"content": {"application/pdf": {}, "image/png": {}}}},
)
def download(report_id: str, session: SessionDep) -> Response:
    data, summary = read_report_file(session, report_id)
    media_type = CONTENT_TYPES.get(str(summary.get("format")), "application/octet-stream")
    headers = {
        "Content-Disposition": f'attachment; filename="{summary["fileName"]}"',
        "ETag": f'"{summary["sha256"]}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
        "X-Report-Id": str(summary["reportId"]),
        "X-Report-Sha256": str(summary["sha256"]),
    }
    return Response(content=data, media_type=media_type, headers=headers)


@router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除报告记录与文件",
)
def remove(report_id: str, session: SessionDep) -> Response:
    delete_report(session, report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

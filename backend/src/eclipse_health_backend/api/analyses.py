"""分析 API（INTERNAL_API_V1 §3）：发起 / 列表 / 详情 / 逐搏分页 / 引擎状态。

- ``POST`` 立即返回 ``202``，分析在后台线程执行；同一记录已有
  ``queued|running`` 分析时幂等返回该分析（不新建）。
- 业务失败（心搏不足、模块崩溃等）不体现在 POST 上，而是落库为
  ``status=failed`` + ``error{code,message}``，通过轮询查询。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..analysis_service import get_analysis_service
from ..db import analysis_repo
from ..db.repositories import get_record_row, list_signal_rows
from ..domain.errors import ConflictError, InvalidInputError, not_found
from .deps import SessionDep

router = APIRouter(tags=["analyses"])

SUPPORTED_ENGINES = ("cardia",)


class AnalysisOptionsIn(BaseModel):
    allowShortRecord: bool = Field(
        default=False, description="允许 <64 搏的短记录（零填充），结果仅供参考"
    )
    tailMode: Literal["pad", "drop"] = Field(
        default="pad", description="末尾不足一个窗口时的处理：pad 左侧覆盖 / drop 丢弃"
    )


class AnalysisCreate(BaseModel):
    engine: str = Field(default="cardia", max_length=64)
    options: AnalysisOptionsIn = Field(default_factory=AnalysisOptionsIn)


class AnalysisAccepted(BaseModel):
    analysisId: str
    recordId: str
    status: str
    engine: str


class AnalysisSummaryModel(BaseModel):
    id: str
    recordId: str
    engine: str
    moduleId: str | None = None
    modelId: str | None = None
    modelVersion: str | None = None
    task: str | None = None
    status: str
    summary: str | None = None
    quality: dict[str, Any] | None = None
    createdAt: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    durationMs: int | None = None
    progress: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    warnings: list[Any] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    beatsTotal: int = 0


class AnalysisDetailModel(AnalysisSummaryModel):
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    beats: list[dict[str, Any]] | None = None
    beatsRef: dict[str, Any] | None = None
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisListModel(BaseModel):
    items: list[AnalysisSummaryModel]


class BeatPageModel(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class EngineStatusModel(BaseModel):
    status: str
    engine: str
    moduleId: str
    modelId: str
    modelVersion: str
    message: str
    startedAt: str | None = None
    readyAt: str | None = None
    warmupSeconds: float | None = None
    mode: str | None = None
    error: str | None = None
    modelCard: dict[str, Any] | None = Field(
        default=None, description="模型卡摘要（参数量、输入契约、类别、局限、非诊断声明）"
    )


def _require_record(session: Any, record_id: str) -> Any:
    row = get_record_row(session, record_id)
    if row is None or row.deleted_at is not None:
        raise not_found("record", record_id)
    return row


@router.post(
    "/records/{record_id}/analyses",
    response_model=AnalysisAccepted,
    status_code=202,
    summary="发起分析（202；同记录进行中分析幂等复用）",
    description=(
        "同一记录已有 `queued`/`running` 分析时，返回该分析并保持 202，不新建任务。\n\n"
        "记录不存在 → 404；记录无波形 → 409 `record_has_no_signal`；"
        "心搏不足、模块崩溃等异步失败体现在轮询结果的 `status=failed` + `error.code`。"
    ),
)
def create_analysis(
    record_id: str, payload: AnalysisCreate, session: SessionDep
) -> JSONResponse:
    _require_record(session, record_id)
    if not list_signal_rows(session, record_id):
        raise ConflictError(
            "record has no signal to analyze",
            code="record_has_no_signal",
            details={"recordId": record_id},
        )
    if payload.engine not in SUPPORTED_ENGINES:
        raise InvalidInputError(
            f"unsupported analysis engine: {payload.engine[:64]}",
            code="unknown_engine",
            details={"supported": list(SUPPORTED_ENGINES)},
        )

    accepted, _reused = get_analysis_service().submit(
        record_id=record_id,
        engine=payload.engine,
        options=payload.options.model_dump(by_alias=True),
    )
    return JSONResponse(status_code=202, content=accepted)


@router.get(
    "/records/{record_id}/analyses",
    response_model=AnalysisListModel,
    summary="按记录列出分析（createdAt 倒序）",
)
def list_analyses(
    record_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisListModel:
    _require_record(session, record_id)
    rows = analysis_repo.list_analysis_rows(session, record_id, limit=limit, offset=offset)
    return AnalysisListModel(items=[analysis_repo.summary_of(row) for row in rows])


@router.get(
    "/analyses/{analysis_id}/beats",
    response_model=BeatPageModel,
    summary="逐搏分页（大记录用）",
)
def get_beats(
    analysis_id: str,
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> BeatPageModel:
    row = analysis_repo.get_analysis_row(session, analysis_id)
    if row is None:
        raise not_found("analysis", analysis_id)
    return BeatPageModel(
        **analysis_repo.beats_page(session, row, offset=offset, limit=limit)
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisDetailModel,
    summary="按 ID 查询分析（默认包含 beats）",
)
def get_analysis(
    analysis_id: str,
    session: SessionDep,
    include_beats: Annotated[bool, Query(alias="includeBeats")] = True,
) -> AnalysisDetailModel:
    row = analysis_repo.get_analysis_row(session, analysis_id)
    if row is None:
        raise not_found("analysis", analysis_id)
    return AnalysisDetailModel(
        **analysis_repo.detail_of(session, row, include_beats=include_beats)
    )


@router.get("/engine", response_model=EngineStatusModel, summary="分析引擎状态")
def get_engine() -> EngineStatusModel:
    return EngineStatusModel(**get_analysis_service().engine_status())


__all__ = ["router"]

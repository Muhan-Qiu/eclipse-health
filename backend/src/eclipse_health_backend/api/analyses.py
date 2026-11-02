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

from ..analysis_service import CARDIA_ENGINE, get_analysis_service
from ..analysis_service.engines import get_engine as find_engine
from ..analysis_service.engines import list_engines
from ..db import analysis_repo
from ..db.repositories import get_record_row, list_signal_rows
from ..domain.errors import ConflictError, InvalidInputError, not_found
from .deps import SessionDep

router = APIRouter(tags=["analyses"])


class AnalysisOptionsIn(BaseModel):
    allowShortRecord: bool = Field(
        default=False, description="允许 <64 搏的短记录（零填充），结果仅供参考"
    )
    tailMode: Literal["pad", "drop"] = Field(
        default="pad", description="末尾不足一个窗口时的处理：pad 左侧覆盖 / drop 丢弃"
    )


class AnalysisCreate(BaseModel):
    engine: str = Field(default=CARDIA_ENGINE, max_length=64)
    options: AnalysisOptionsIn = Field(default_factory=AnalysisOptionsIn)
    force: bool = Field(
        default=False,
        description="取消该记录上仍在 queued/running 的旧分析后重新发起",
    )


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


class EngineDescriptorModel(BaseModel):
    id: str
    name: str
    moduleId: str
    modelId: str
    modelVersion: str
    available: bool
    reason: str | None = Field(default=None, description="不可用时的用户可读原因")


class EngineCatalogModel(BaseModel):
    items: list[EngineDescriptorModel]


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
    if find_engine(payload.engine) is None:
        raise InvalidInputError(
            f"unsupported analysis engine: {payload.engine[:64]}",
            code="unknown_engine",
            details={"supported": [engine.id for engine in list_engines()]},
        )

    accepted, _reused = get_analysis_service().submit(
        record_id=record_id,
        engine=payload.engine,
        options=payload.options.model_dump(by_alias=True),
        force=payload.force,
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
    "/analyses/engines",
    response_model=EngineCatalogModel,
    summary="分析引擎目录（含可用性）",
    description=(
        "返回注册表中的全部引擎，供 UI 选择与「重新分析」使用。\n\n"
        "运行时就绪状态（预热/失败）仍由 `GET /engine` 给出；二者职责不同。"
    ),
)
def list_available_engines() -> EngineCatalogModel:
    return EngineCatalogModel(
        items=[EngineDescriptorModel(**item.to_dict()) for item in list_engines()]
    )


# --------------------------------------------------------------------------- #
# 运行控制（队列 / 取消 / 重试 / 修复）
# --------------------------------------------------------------------------- #


def _require_analysis_row(session: Any, analysis_id: str) -> Any:
    row = analysis_repo.get_analysis_row(session, analysis_id)
    if row is None:
        raise not_found("analysis", analysis_id)
    return row


@router.get(
    "/analyses/queue",
    summary="分析队列状态（暂停/运行中/排队数/引擎状态）",
    description=(
        "供 UI 与智能体诊断卡死：返回当前运行的分析、已运行秒数、活跃分析行。"
        "看门狗会把超过 `jobTimeoutSeconds` 且 worker 未持有的 running 行标记为中断。"
    ),
)
def get_queue_status() -> dict[str, Any]:
    return get_analysis_service().queue_status()


@router.post("/analyses/queue/pause", summary="暂停领取新的分析任务")
def pause_analysis_queue() -> dict[str, Any]:
    return get_analysis_service().pause_queue()


@router.post("/analyses/queue/resume", summary="恢复分析队列")
def resume_analysis_queue() -> dict[str, Any]:
    return get_analysis_service().resume_queue()


@router.post(
    "/analyses/recover",
    summary="修复卡死的分析（把超时的 queued/running 标记为 interrupted）",
)
def recover_stalled_analyses(
    max_age_s: Annotated[float | None, Query(alias="maxAgeSeconds", ge=0)] = None,
) -> dict[str, Any]:
    service = get_analysis_service()
    recovered = service.repair_stalled(max_age_s=max_age_s)
    return {"recovered": recovered, "queue": service.queue_status()}


@router.post(
    "/analyses/{analysis_id}/cancel",
    summary="取消一条分析（运行中会中断引擎，队列立即继续）",
)
def cancel_analysis(analysis_id: str, session: SessionDep) -> dict[str, Any]:
    _require_analysis_row(session, analysis_id)
    return get_analysis_service().cancel(analysis_id)


@router.post(
    "/analyses/{analysis_id}/retry",
    response_model=AnalysisAccepted,
    status_code=202,
    summary="按原参数重试一条分析（先取消旧任务）",
)
def retry_analysis(analysis_id: str, session: SessionDep) -> JSONResponse:
    _require_analysis_row(session, analysis_id)
    accepted, _reused = get_analysis_service().retry(analysis_id)
    return JSONResponse(status_code=202, content=accepted)


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

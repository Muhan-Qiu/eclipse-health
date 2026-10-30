"""两步导入 API（契约 §2）。

``POST /imports/preview`` → 预览；``POST /imports/{importId}/commit`` → 入库；
``DELETE /imports/{importId}`` → 丢弃。B2-01 负责把本 router 挂到 ``/api/v1``。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..api.deps import SessionDep
from ..db.repositories import (
    ensure_default_member,
    get_member_row,
)
from ..domain.common import utc_now
from ..domain.errors import not_found
from ..domain.models import HealthRecord
from . import limits, store
from .base import ImportAdapter, ImportSource, ParseParameters
from .errors import (
    ImportApiError,
    ImportNotFoundError,
    ImportTooLargeError,
    invalid_file,
    unsupported_format,
)
from .persist import create_record_from_parsed
from .registry import AdapterRegistry, build_default_registry
from .samples import import_sample

router = APIRouter(prefix="/imports", tags=["imports"])
REGISTRY: AdapterRegistry = build_default_registry()

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- models
class PreviewRequires(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samplingRate: bool
    lead: bool
    unit: bool


class PreviewBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nSamples: int | None
    samples: list[float]


class ImportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    importId: str
    format: str
    adapterId: str
    fileNameHash: str
    fileHash: str
    samplingRate: float | None
    leads: list[str]
    durationSec: float | None
    unit: str
    requires: PreviewRequires
    warnings: list[dict[str, Any]]
    preview: PreviewBlock
    hasAnnotations: bool = False
    annotationCount: int = 0


class ImportParameters(BaseModel):
    """参数校正：采样率/导联/单位/极性 + CSV 的列选择。"""

    model_config = ConfigDict(extra="allow")

    samplingRate: float | None = Field(default=None, gt=0, le=1_000_000)
    lead: str | None = Field(default=None, max_length=16)
    unit: str | None = Field(default=None, max_length=32)
    polarity: Literal["normal", "inverted"] = "normal"
    leadColumn: str | int | None = None
    timeColumn: str | int | None = None

    def to_parse_parameters(self) -> ParseParameters:
        return ParseParameters(
            sampling_rate=self.samplingRate,
            lead=self.lead,
            unit=self.unit,
            polarity=self.polarity,
            lead_column=None if self.leadColumn is None else str(self.leadColumn),
            time_column=None if self.timeColumn is None else str(self.timeColumn),
        )


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memberId: str = Field(min_length=1, max_length=64)
    capturedAt: AwareDatetime
    timezone: str = Field(default="UTC", max_length=64)
    tags: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)
    parameters: ImportParameters = Field(default_factory=ImportParameters)


class ImportCommitResponse(BaseModel):
    recordId: str
    record: HealthRecord


class SampleImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memberId: str | None = Field(default=None, min_length=1, max_length=64)
    capturedAt: AwareDatetime | None = None
    timezone: str = Field(default="UTC", max_length=64)
    startAnalysis: bool = False


class SampleImportResponse(BaseModel):
    recordId: str
    analysisId: str | None = None


# ------------------------------------------------------------------- helpers
def _validate_path(raw: str) -> Path:
    candidate = Path(raw.strip().strip('"'))
    if not candidate.is_absolute():
        raise invalid_file(
            "path 必须是绝对路径（仅调试用）",
            code="invalid_path",
            details={"path": raw[:200]},
        )
    if ".." in candidate.parts:
        raise invalid_file(
            "path 不能包含 .. 段", code="invalid_path", details={"path": raw[:200]}
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise invalid_file(
            "path 不存在或不可读", code="invalid_path", details={"path": raw[:200]}
        ) from exc
    if resolved.is_file() and resolved.stat().st_size > limits.MAX_UPLOAD_BYTES:
        raise ImportTooLargeError(
            "文件超过大小上限",
            details={"limit": limits.MAX_UPLOAD_BYTES, "bytes": resolved.stat().st_size},
        )
    if not resolved.is_file() and not resolved.is_dir():
        raise invalid_file("path 不是普通文件或目录", code="invalid_path")
    return resolved


def _materialize_source(
    workspace: Path, upload: UploadFile | None, raw_path: str | None
) -> ImportSource:
    has_file = upload is not None and bool(upload.filename)
    if has_file and raw_path:
        raise invalid_file("file 与 path 只能提供其一")
    if not has_file and not raw_path:
        raise invalid_file("请提供 file（multipart）或 path（本地调试）")

    if has_file:
        assert upload is not None
        saved, file_hash, name_hash = store.save_upload(workspace, upload)
        source = ImportSource(
            kind="upload",
            path=saved,
            workspace=workspace,
            original_name=Path(upload.filename or "").name,
            file_name_hash=name_hash,
            file_hash=file_hash,
        )
    else:
        resolved = _validate_path(raw_path or "")
        source = ImportSource(
            kind="path",
            path=resolved,
            workspace=workspace,
            original_name=resolved.name,
            file_name_hash=store.filename_hash(resolved.name),
            file_hash=store.hash_path_source(resolved),
        )

    if store.is_zip(source.path):
        source.extracted_dir = store.extract_zip(source.path, workspace)
    return source


def _meta_source(workspace: Path, source: ImportSource) -> dict[str, Any]:
    if source.kind == "upload":
        relative = source.path.relative_to(workspace).as_posix()
    else:
        relative = str(source.path)
    return {
        "kind": source.kind,
        "name": source.original_name,
        "path": relative,
        "extracted": source.extracted_dir is not None,
    }


def _source_from_meta(workspace: Path, meta: dict[str, Any]) -> ImportSource:
    info = meta.get("source") or {}
    kind = str(info.get("kind") or "")
    if kind == "upload":
        path = store.workspace_file(workspace, str(info.get("path") or ""))
        if not path.is_file():
            raise ImportNotFoundError(
                "import source file is missing", code="import_expired"
            )
    elif kind == "path":
        path = Path(str(info.get("path") or ""))
        if not path.exists():
            raise ImportNotFoundError(
                "import source path is gone", code="import_source_missing"
            )
    else:
        raise ImportNotFoundError("import workspace is corrupted", code="import_not_found")

    extracted = None
    if info.get("extracted"):
        candidate = workspace / store.EXTRACTED_DIR
        if candidate.is_dir():
            extracted = candidate
    return ImportSource(
        kind=kind,
        path=path,
        workspace=workspace,
        original_name=info.get("name"),
        file_name_hash=str(meta.get("fileNameHash") or ""),
        file_hash=str(meta.get("fileHash") or ""),
        extracted_dir=extracted,
    )


def _require_adapter(adapter_id: str) -> ImportAdapter:
    adapter = REGISTRY.find(adapter_id)
    if adapter is None or not adapter.supported:
        raise unsupported_format(
            "该格式的适配器不可用", details={"adapterId": adapter_id}
        )
    return adapter


def _enforce_requirements(meta: dict[str, Any], parameters: ImportParameters) -> None:
    requires = meta.get("requires") or {}
    if requires.get("samplingRate") and parameters.samplingRate is None:
        raise ImportApiError(
            "请确认采样率后提交", code="sampling_rate_required", details=requires
        )
    if requires.get("lead") and not parameters.lead:
        raise ImportApiError("请确认导联后提交", code="lead_required", details=requires)
    if requires.get("unit") and not parameters.unit:
        raise ImportApiError("请确认单位后提交", code="unit_required", details=requires)


@router.post(
    "/samples/{sample_id}",
    response_model=SampleImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="导入内置 MIT-BIH 示例记录（只读白名单）",
)
def import_sample_record(
    sample_id: str,
    session: SessionDep,
    payload: SampleImportRequest | None = None,
) -> SampleImportResponse:
    """A1 首次引导：一次调用生成一条真实的导入记录。

    样本来自 ``backend/resources/samples``，样例只允许 100/200/208；
    未知 ID → 404 ``sample_not_found``。分析失败不影响记录创建。
    """
    request = payload or SampleImportRequest()
    if request.memberId:
        if get_member_row(session, request.memberId) is None:
            raise not_found("member", request.memberId)
        member_id = request.memberId
    else:
        member_id = ensure_default_member(session).id

    record = import_sample(
        session,
        REGISTRY,
        sample_id=sample_id,
        member_id=member_id,
        captured_at=request.capturedAt or utc_now(),
        timezone=request.timezone,
    )

    analysis_id: str | None = None
    if request.startAnalysis:
        try:
            from ..analysis_service import get_analysis_service

            accepted, _reused = get_analysis_service().submit(
                record_id=record.id, engine="cardia", options={}
            )
            analysis_id = str(accepted.get("analysisId") or "") or None
        except Exception:
            logger.warning("sample import: analysis start failed", exc_info=True)

    return SampleImportResponse(recordId=record.id, analysisId=analysis_id)


# ----------------------------------------------------------------- endpoints
@router.post("/preview", response_model=ImportPreviewResponse, summary="预览导入文件")
def preview_import(
    file: Annotated[UploadFile | None, File()] = None,
    path: Annotated[str | None, Form()] = None,
    hint_format: Annotated[str, Form(alias="hintFormat")] = "auto",
) -> ImportPreviewResponse:
    store.cleanup_expired()
    import_id = store.new_import_id()
    workspace = store.create_workspace(import_id)
    try:
        source = _materialize_source(workspace, file, path)
        adapter, detection = REGISTRY.detect(source, hint_format)
        preview = adapter.preview(source)
        meta = {
            "importId": import_id,
            "createdAt": utc_now().isoformat(),
            "format": detection.format,
            "adapterId": adapter.adapter_id,
            "adapterVersion": adapter.adapter_version,
            "fileNameHash": source.file_name_hash,
            "fileHash": source.file_hash,
            "requires": preview.requires,
            "leads": preview.leads,
            "samplingRate": preview.sampling_rate,
            "durationSec": preview.duration_sec,
            "unit": preview.unit,
            "source": _meta_source(workspace, source),
        }
        store.write_meta(workspace, meta)
    except BaseException:
        store.delete_workspace_path(workspace)
        raise

    return ImportPreviewResponse(
        importId=import_id,
        format=detection.format,
        adapterId=adapter.adapter_id,
        fileNameHash=source.file_name_hash,
        fileHash=source.file_hash,
        samplingRate=preview.sampling_rate,
        leads=preview.leads,
        durationSec=preview.duration_sec,
        unit=preview.unit,
        requires=PreviewRequires(**preview.requires),
        warnings=preview.warnings,
        preview=PreviewBlock(nSamples=preview.n_samples, samples=preview.samples),
        hasAnnotations=preview.has_annotations,
        annotationCount=preview.annotation_count,
    )


@router.post(
    "/{import_id}/commit",
    response_model=ImportCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交预览并创建记录",
)
def commit_import(
    import_id: str,
    payload: ImportCommitRequest,
    session: SessionDep,
) -> ImportCommitResponse:
    workspace, meta = store.load_workspace(import_id)
    if get_member_row(session, payload.memberId) is None:
        raise not_found("member", payload.memberId)
    adapter = _require_adapter(str(meta.get("adapterId") or ""))
    _enforce_requirements(meta, payload.parameters)

    source = _source_from_meta(workspace, meta)
    parsed = adapter.parse(source, payload.parameters.to_parse_parameters())

    record = create_record_from_parsed(
        session,
        parsed,
        member_id=payload.memberId,
        captured_at=payload.capturedAt,
        timezone=payload.timezone,
        module_id=adapter.adapter_id,
        tags=payload.tags,
        notes=payload.notes,
        file_name_hash=str(meta.get("fileNameHash") or ""),
        file_hash=str(meta.get("fileHash") or ""),
    )

    store.delete_workspace(import_id)
    return ImportCommitResponse(recordId=record.id, record=record)


@router.delete(
    "/{import_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="丢弃导入工作区",
)
def discard_import(import_id: str) -> Response:
    store.delete_workspace(import_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["REGISTRY", "router"]

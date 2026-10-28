"""两步导入 API（契约 §2）。

``POST /imports/preview`` → 预览；``POST /imports/{importId}/commit`` → 入库；
``DELETE /imports/{importId}`` → 丢弃。B2-01 负责把本 router 挂到 ``/api/v1``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, File, Form, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from ..api.deps import SessionDep
from ..db.repositories import add_record, add_signal, get_member_row, make_signal
from ..domain.common import utc_now
from ..domain.errors import InvalidInputError, not_found
from ..domain.ids import new_id
from ..domain.models import HealthRecord, Provenance, Signal, SourceInfo
from ..storage.files import delete_signal, write_signal
from . import limits, store
from .base import ImportAdapter, ImportSource, ParsedImport, ParseParameters
from .errors import (
    ImportApiError,
    ImportNotFoundError,
    ImportTooLargeError,
    invalid_file,
    unsupported_format,
)
from .registry import AdapterRegistry, build_default_registry

router = APIRouter(prefix="/imports", tags=["imports"])
REGISTRY: AdapterRegistry = build_default_registry()

RECORD_TYPE = "org.eclipsehealth.ecg"


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


def _record_metadata(parsed: ParsedImport) -> dict[str, Any]:
    metadata = dict(parsed.metadata)
    metadata["hasAnnotations"] = bool(parsed.has_annotations)
    metadata["annotationCount"] = int(parsed.annotation_count)
    codes: list[str] = []
    for item in parsed.warnings:
        code = str(item.get("code", ""))
        if code and code not in codes:
            codes.append(code)
    if codes:
        metadata["importWarnings"] = codes[:20]
    return metadata


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

    now = utc_now()
    record_id = new_id("record")
    written: list[str] = []
    signals: list[Signal] = []
    try:
        for lead in parsed.leads:
            signal_id = new_id("signal")
            relative_path, digest, _size = write_signal(signal_id, lead.samples)
            written.append(relative_path)
            signals.append(
                make_signal(
                    signal_id=signal_id,
                    record_id=record_id,
                    lead=lead.lead,
                    fs=parsed.sampling_rate,
                    unit="mV",
                    n_samples=int(np.asarray(lead.samples).size),
                    relative_path=relative_path,
                    sha256=digest,
                    created_at=now,
                )
            )

        record = HealthRecord(
            id=record_id,
            memberId=payload.memberId,
            recordType=RECORD_TYPE,
            moduleId=adapter.adapter_id,
            capturedAt=payload.capturedAt,
            timezone=payload.timezone,
            source=SourceInfo(kind="import"),
            samplingRate=parsed.sampling_rate,
            leads=[lead.lead for lead in parsed.leads],
            durationSec=parsed.duration_sec,
            unit="mV",
            signalIds=[signal.id for signal in signals],
            tags=payload.tags,
            notes=payload.notes,
            metadata=_record_metadata(parsed),
            provenance=Provenance(
                fileNameHash=str(meta.get("fileNameHash") or ""),
                fileHash=str(meta.get("fileHash") or ""),
                adapterVersion=adapter.adapter_version,
            ),
            createdAt=now,
            updatedAt=now,
        )
    except PydanticValidationError as exc:
        for path in written:
            delete_signal(path)
        raise InvalidInputError(
            "记录校验失败",
            code="record_invalid",
            details=jsonable_encoder(exc.errors(), custom_encoder={Exception: str}),
        ) from exc
    except BaseException:
        for path in written:
            delete_signal(path)
        raise

    try:
        add_record(session, record, commit=False)
        for signal in signals:
            add_signal(session, signal, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        for path in written:
            delete_signal(path)
        raise

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

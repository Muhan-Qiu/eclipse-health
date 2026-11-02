"""把已解析的导入结果落库。

``importers.api`` 的 commit 与 ``importers.samples`` 的示例导入共用这一段：
两边走同一个适配器解析结果，避免各写一份记录/信号写入逻辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..db.models import RecordTable
from ..db.repositories import add_record, add_signal, make_signal
from ..domain.common import utc_now
from ..domain.errors import InvalidInputError
from ..domain.ids import new_id
from ..domain.models import HealthRecord, Provenance, Signal, SourceInfo
from ..storage.files import delete_signal, write_signal
from .base import ParsedImport

RECORD_TYPE = "org.eclipsehealth.ecg"
HEALTH_RECORD_PREFIX = "org.eclipsehealth.health."

# 与 API 的 recordCounts 键一致。
KIND_COUNT_KEYS = {
    "steps": "steps",
    "heart-rate": "heartRate",
    "sleep": "sleep",
    "body-mass": "bodyMass",
    "blood-pressure": "bloodPressure",
    "stress": "stress",
    "workout": "workout",
    "respiratory-rate": "respiratoryRate",
    "ecg": "ecg",
}

logger = logging.getLogger(__name__)


def record_metadata(parsed: ParsedImport) -> dict[str, Any]:
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


def create_record_from_parsed(
    session: Session,
    parsed: ParsedImport,
    *,
    member_id: str,
    captured_at: datetime,
    timezone: str,
    module_id: str | None,
    tags: list[str] | None = None,
    notes: str = "",
    file_name_hash: str = "",
    file_hash: str = "",
    record_type: str = RECORD_TYPE,
    extra_metadata: dict[str, Any] | None = None,
) -> HealthRecord:
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

        metadata = record_metadata(parsed)
        if extra_metadata:
            metadata.update(extra_metadata)
        record = HealthRecord(
            id=record_id,
            memberId=member_id,
            recordType=record_type,
            moduleId=module_id,
            capturedAt=captured_at,
            timezone=timezone,
            source=SourceInfo(kind="import"),
            samplingRate=parsed.sampling_rate,
            leads=[lead.lead for lead in parsed.leads],
            durationSec=parsed.duration_sec,
            unit="mV",
            signalIds=[signal.id for signal in signals],
            tags=list(tags or []),
            notes=notes,
            metadata=metadata,
            provenance=Provenance(
                fileNameHash=file_name_hash,
                fileHash=file_hash,
                adapterVersion=parsed.adapter_version,
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

    return record


@dataclass(slots=True)
class BundleCommitResult:
    records: list[HealthRecord] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    skipped: int = 0
    failed: int = 0
    duplicate_file: bool = False


def _bundle_type_filter() -> Any:
    return or_(
        RecordTable.record_type == RECORD_TYPE,
        RecordTable.record_type.startswith(HEALTH_RECORD_PREFIX),
    )


def _existing_external_ids(session: Session) -> set[str]:
    """已入库的去重键；只扫描 ECG 与健康记录，避免把所有记录读进内存。"""
    extract = func.json_extract(RecordTable.data, "$.metadata.externalId")
    statement = select(extract).where(
        _bundle_type_filter(),
        RecordTable.deleted_at.is_(None),
        extract.is_not(None),
    )
    return {str(value) for value in session.exec(statement) if value}


def _file_already_imported(session: Session, file_hash: str) -> bool:
    extract = func.json_extract(RecordTable.data, "$.provenance.fileHash")
    statement = (
        select(RecordTable.id)
        .where(
            _bundle_type_filter(),
            RecordTable.deleted_at.is_(None),
            extract == file_hash,
        )
        .limit(1)
    )
    return session.exec(statement).first() is not None


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def create_health_record(
    session: Session,
    draft: Any,
    *,
    member_id: str,
    timezone: str,
    module_id: str | None,
    file_name_hash: str = "",
    file_hash: str = "",
    adapter_version: str | None = None,
    import_source: str = "",
    tags: list[str] | None = None,
    notes: str = "",
    fallback_captured_at: datetime,
) -> HealthRecord:
    """把一条非波形健康数据写成 HealthRecord（无信号、payload 带 value/unit/时间）。"""
    now = utc_now()
    metadata: dict[str, Any] = {
        "importSource": import_source,
        "externalId": draft.external_id,
    }
    metadata.update(draft.metadata)
    source_app = (draft.source_app or import_source or None)
    record = HealthRecord(
        id=new_id("record"),
        memberId=member_id,
        recordType=draft.record_type,
        moduleId=module_id,
        capturedAt=draft.captured_at or fallback_captured_at,
        timezone=timezone,
        source=SourceInfo(kind="import", app=source_app[:64] if source_app else None),
        samplingRate=None,
        leads=[],
        durationSec=draft.duration_sec,
        unit=draft.unit or "1",
        signalIds=[],
        tags=list(tags or []),
        notes=notes,
        metadata=metadata,
        payload=draft.payload,
        provenance=Provenance(
            fileNameHash=file_name_hash or None,
            fileHash=file_hash or None,
            adapterVersion=adapter_version,
        ),
        createdAt=now,
        updatedAt=now,
    )
    add_record(session, record, commit=False)
    return record


def commit_import_bundle(
    session: Session,
    parsed: ParsedImport,
    *,
    member_id: str,
    captured_at: datetime,
    timezone: str,
    module_id: str | None,
    tags: list[str] | None = None,
    notes: str = "",
    file_name_hash: str = "",
    file_hash: str = "",
) -> BundleCommitResult:
    """批量写入健康数据包。

    去重：整包 ``provenance.fileHash`` 已存在 → 全部跳过；否则逐条按
    ``metadata.externalId`` 跳过。单条失败只计数，不回滚已写入的记录。
    """
    ecg_items = list(parsed.ecg_records)
    drafts = list(parsed.health_records)
    total = len(ecg_items) + len(drafts)
    result = BundleCommitResult()
    import_source = str(parsed.import_source or parsed.metadata.get("importSource") or "")

    if file_hash and _file_already_imported(session, file_hash):
        result.duplicate_file = True
        result.skipped = total
        return result

    existing = _existing_external_ids(session)

    for item in ecg_items:
        external_id = str(item.metadata.get("externalId") or "")
        if external_id and external_id in existing:
            result.skipped += 1
            continue
        try:
            record = create_record_from_parsed(
                session,
                item,
                member_id=member_id,
                captured_at=item.captured_at or captured_at,
                timezone=timezone,
                module_id=module_id,
                tags=tags,
                notes=notes,
                file_name_hash=file_name_hash,
                file_hash=file_hash,
                extra_metadata={
                    "importSource": import_source,
                    "externalId": external_id,
                },
            )
        except Exception:
            logger.warning("bundle import: ECG record failed", exc_info=True)
            session.rollback()
            result.failed += 1
            continue
        if external_id:
            existing.add(external_id)
        result.records.append(record)
        _bump(result.counts, KIND_COUNT_KEYS["ecg"])

    for draft in drafts:
        if draft.external_id and draft.external_id in existing:
            result.skipped += 1
            continue
        try:
            record = create_health_record(
                session,
                draft,
                member_id=member_id,
                timezone=timezone,
                module_id=module_id,
                file_name_hash=file_name_hash,
                file_hash=file_hash,
                adapter_version=parsed.adapter_version,
                import_source=import_source,
                tags=tags,
                notes=notes,
                fallback_captured_at=captured_at,
            )
            session.commit()
        except Exception:
            logger.warning("bundle import: health record failed", exc_info=True)
            session.rollback()
            result.failed += 1
            continue
        if draft.external_id:
            existing.add(draft.external_id)
        result.records.append(record)
        _bump(result.counts, KIND_COUNT_KEYS.get(draft.kind, draft.kind))

    return result


__all__ = [
    "KIND_COUNT_KEYS",
    "RECORD_TYPE",
    "BundleCommitResult",
    "commit_import_bundle",
    "create_health_record",
    "create_record_from_parsed",
    "record_metadata",
]

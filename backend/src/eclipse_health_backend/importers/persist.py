"""把已解析的导入结果落库。

``importers.api`` 的 commit 与 ``importers.samples`` 的示例导入共用这一段：
两边走同一个适配器解析结果，避免各写一份记录/信号写入逻辑。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError as PydanticValidationError
from sqlmodel import Session

from ..db.repositories import add_record, add_signal, make_signal
from ..domain.common import utc_now
from ..domain.errors import InvalidInputError
from ..domain.ids import new_id
from ..domain.models import HealthRecord, Provenance, Signal, SourceInfo
from ..storage.files import delete_signal, write_signal
from .base import ParsedImport

RECORD_TYPE = "org.eclipsehealth.ecg"


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


__all__ = ["RECORD_TYPE", "create_record_from_parsed", "record_metadata"]

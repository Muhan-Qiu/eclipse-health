"""把 Agent 候选写入核心 records/signals 表。

- 非波形记录：直接构造 ``HealthRecord``，payload 保留 kind/value/unit/证据；
- ECG：把 output/ 下的 CSV / float32 转成 mV 采样，走现有 ``create_record_from_parsed``
  波形管线；
- 幂等：``metadata.externalId`` 由文件哈希 + 来源 + kind + 时间 + 值决定。
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlmodel import Session, select

from ..db.models import RecordTable
from ..db.repositories import add_record, get_record_row, update_record_row
from ..domain.common import utc_now
from ..domain.errors import InvalidInputError
from ..domain.ids import new_id
from ..domain.models import HealthRecord, Provenance, SourceInfo
from ..importers.base import ParsedImport, ParsedLead
from ..importers.persist import create_record_from_parsed
from ..importers.store import filename_hash
from . import limits, store
from .errors import RecordValidationError
from .kinds import ADAPTER_VERSION, external_id

logger = logging.getLogger(__name__)


def existing_external_ids(session: Session, ids: set[str]) -> set[str]:
    if not ids:
        return set()
    extract = func.json_extract(RecordTable.data, "$.metadata.externalId")
    found: set[str] = set()
    values = list(ids)
    for start in range(0, len(values), 400):
        chunk = values[start : start + 400]
        statement = select(extract).where(
            RecordTable.deleted_at.is_(None), extract.in_(chunk)
        )
        found.update(str(value) for value in session.exec(statement) if value)
    return found


def _source_info(source: dict[str, Any]) -> SourceInfo:
    kind = str(source.get("kind") or "unknown")
    mapped = {"device": "device", "app": "file", "manual": "manual"}.get(kind, "import")
    return SourceInfo(
        kind=mapped,
        app=source.get("app"),
        device=source.get("device"),
        manufacturer=source.get("manufacturer"),
    )


def _evidence(proposal: dict[str, Any]) -> dict[str, Any]:
    evidence = proposal.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def _proposal_eid(meta: dict[str, Any], proposal: dict[str, Any]) -> str:
    file_hash = store.file_hash_for(meta, str(_evidence(proposal).get("file") or ""))
    return external_id(
        file_hash=file_hash,
        source=proposal.get("source") or {},
        kind=str(proposal.get("kind") or ""),
        start_at=str(proposal.get("startAt") or ""),
        end_at=proposal.get("endAt"),
        value=proposal.get("value"),
    )


def _metadata(meta: dict[str, Any], proposal: dict[str, Any], eid: str) -> dict[str, Any]:
    return {
        "importSource": "import-agent",
        "externalId": eid,
        "agentSessionId": meta.get("sessionId"),
        "confidence": proposal.get("confidence"),
        "evidence": _evidence(proposal),
    }


def _create_numeric(
    session: Session,
    *,
    meta: dict[str, Any],
    proposal: dict[str, Any],
    eid: str,
    member_id: str,
    timezone: str,
) -> HealthRecord:
    now = utc_now()
    evidence = _evidence(proposal)
    record = HealthRecord(
        id=new_id("record"),
        memberId=member_id,
        recordType=str(proposal.get("recordType") or ""),
        moduleId=None,
        capturedAt=datetime.fromisoformat(str(proposal.get("startAt"))),
        timezone=timezone,
        source=_source_info(proposal.get("source") or {}),
        samplingRate=None,
        leads=[],
        durationSec=proposal.get("durationSec"),
        unit=str(proposal.get("unit") or "1"),
        signalIds=[],
        tags=list(proposal.get("tags") or []),
        notes=str(proposal.get("notes") or ""),
        metadata=_metadata(meta, proposal, eid),
        payload=dict(proposal.get("payload") or {}),
        provenance=Provenance(
            fileNameHash=filename_hash(str(evidence.get("file") or "")),
            fileHash=store.file_hash_for(meta, str(evidence.get("file") or "")) or None,
            adapterVersion=ADAPTER_VERSION,
        ),
        createdAt=now,
        updatedAt=now,
    )
    add_record(session, record, commit=True)
    return record


# --------------------------------------------------------------------------- #
# ECG 波形
# --------------------------------------------------------------------------- #


def _read_csv_waveform(
    path: Path, waveform: dict[str, Any]
) -> tuple[np.ndarray, float | None]:
    encoding = store.detect_encoding(path)
    column = waveform.get("column", 1)
    if column is None:
        column = 1
    time_column = waveform.get("timeColumn")
    header: list[str] | None = None
    samples: list[float] = []
    times: list[float] = []
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for index, raw in enumerate(reader):
            if not raw:
                continue
            if index == 0:
                probe_index = column if isinstance(column, int) else None
                looks_numeric = (
                    probe_index is not None
                    and probe_index < len(raw)
                    and _to_float(raw[probe_index]) is not None
                )
                if not looks_numeric:
                    header = [cell.strip() for cell in raw]
                    continue
            if isinstance(column, str):
                if header is None or column not in header:
                    raise RecordValidationError(
                        "waveform column not found in CSV header",
                        code="ecg_invalid_waveform",
                        details={"column": column},
                    )
                column_index = header.index(column)
            else:
                column_index = int(column)
            time_index: int | None = None
            if time_column is not None:
                if isinstance(time_column, str):
                    if header is None or time_column not in header:
                        raise RecordValidationError(
                            "waveform timeColumn not found in CSV header",
                            code="ecg_invalid_waveform",
                            details={"timeColumn": time_column},
                        )
                    time_index = header.index(time_column)
                else:
                    time_index = int(time_column)
            if column_index >= len(raw):
                continue
            value = _to_float(raw[column_index])
            if value is None:
                continue
            samples.append(value)
            if time_index is not None and time_index < len(raw):
                time_value = _to_float(raw[time_index])
                if time_value is not None:
                    times.append(time_value)
            if len(samples) > limits.MAX_ECG_SAMPLES:
                raise RecordValidationError(
                    "ECG has too many samples",
                    code="ecg_too_large",
                    details={"limit": limits.MAX_ECG_SAMPLES},
                )
    if len(samples) < 2:
        raise RecordValidationError(
            "ECG CSV contains fewer than 2 samples", code="ecg_invalid_waveform"
        )
    fs: float | None = None
    if len(times) >= 2:
        duration = times[-1] - times[0]
        if duration > 0:
            fs = (len(times) - 1) / duration
    return np.asarray(samples, dtype=np.float64), fs


def _to_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _read_f32_waveform(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) % 4 != 0:
        raise RecordValidationError(
            "float32 waveform size must be a multiple of 4 bytes",
            code="ecg_invalid_waveform",
            details={"bytes": len(data)},
        )
    array = np.frombuffer(data, dtype="<f4")
    if array.size > limits.MAX_ECG_SAMPLES:
        raise RecordValidationError(
            "ECG has too many samples",
            code="ecg_too_large",
            details={"limit": limits.MAX_ECG_SAMPLES},
        )
    return array.astype(np.float64)


def load_waveform(
    workspace: Path, proposal: dict[str, Any]
) -> tuple[np.ndarray, float, str]:
    waveform = proposal.get("waveform") or {}
    relative = str(waveform.get("file") or "")
    # 兼容历史候选里的 "output/ecg.csv"；磁盘路径是 workspace/output/<file>。
    if relative.lower().startswith("output/"):
        relative = relative[len("output/") :]
    path = store.safe_join(workspace / store.OUTPUT_DIR, relative)
    if not path.is_file():
        raise RecordValidationError(
            "waveform file is missing from output/",
            code="ecg_waveform_missing",
            details={"file": relative},
        )
    size = path.stat().st_size
    if size > limits.MAX_ECG_FILE_BYTES:
        raise RecordValidationError(
            "waveform file is too large",
            code="ecg_too_large",
            details={"bytes": size, "limit": limits.MAX_ECG_FILE_BYTES},
        )
    fmt = str(waveform.get("format") or "csv")
    if fmt == "f32":
        samples = _read_f32_waveform(path)
        inferred_fs = None
    else:
        samples, inferred_fs = _read_csv_waveform(path, waveform)
    if samples.size > limits.MAX_ECG_SAMPLES:
        raise RecordValidationError(
            "ECG has too many samples",
            code="ecg_too_large",
            details={"limit": limits.MAX_ECG_SAMPLES},
        )
    if not np.isfinite(samples).all():
        raise RecordValidationError(
            "waveform contains non-finite samples", code="ecg_invalid_waveform"
        )

    value = proposal.get("value") or {}
    fs = waveform.get("samplingRate") or (value.get("samplingRate") if isinstance(value, dict) else None)
    fs = float(fs) if fs else inferred_fs
    if not fs or fs <= 0 or fs > 100_000:
        raise RecordValidationError(
            "ECG sampling rate is required (waveform.samplingRate or a time column)",
            code="ecg_sampling_rate_required",
        )

    unit = str(waveform.get("unit") or proposal.get("unit") or "mV")
    if unit == "uV":
        samples = samples * 0.001
    elif unit == "V":
        samples = samples * 1000.0
    elif unit != "mV":
        raise RecordValidationError(
            "ECG unit must be mV, uV or V", code="invalid_unit", details={"unit": unit}
        )
    lead = str(waveform.get("lead") or (value.get("lead") if isinstance(value, dict) else None) or "I")
    return samples, fs, lead


def _create_ecg(
    session: Session,
    *,
    workspace: Path,
    meta: dict[str, Any],
    proposal: dict[str, Any],
    eid: str,
    member_id: str,
    timezone: str,
) -> HealthRecord:
    samples, fs, lead = load_waveform(workspace, proposal)
    parsed = ParsedImport(
        adapter_id="org.eclipsehealth.import-agent",
        adapter_version=ADAPTER_VERSION,
        format="agent-csv",
        sampling_rate=fs,
        duration_sec=float(samples.size) / fs,
        leads=[ParsedLead(lead=lead, samples=samples.astype(np.float64))],
        primary_lead=lead,
    )
    evidence = _evidence(proposal)
    record = create_record_from_parsed(
        session,
        parsed,
        member_id=member_id,
        captured_at=datetime.fromisoformat(str(proposal.get("startAt"))),
        timezone=timezone,
        module_id=None,
        tags=list(proposal.get("tags") or []),
        notes=str(proposal.get("notes") or ""),
        file_name_hash=filename_hash(str(evidence.get("file") or "")),
        file_hash=store.file_hash_for(meta, str(evidence.get("file") or "")),
        extra_metadata=_metadata(meta, proposal, eid),
    )
    row = get_record_row(session, record.id)
    if row is not None:
        data = record.model_dump(by_alias=True, mode="json")
        data["payload"] = dict(proposal.get("payload") or {})
        data["unit"] = "mV"
        data["updatedAt"] = utc_now().isoformat()
        update_record_row(session, row, HealthRecord.model_validate(data))
    return record


# --------------------------------------------------------------------------- #
# 选择与提交
# --------------------------------------------------------------------------- #


def select_proposals(
    proposals: list[dict[str, Any]], requested: list[Any] | None
) -> list[dict[str, Any]]:
    if not requested:
        return list(proposals)
    by_id = {str(item.get("id")): item for item in proposals}
    by_fingerprint = {str(item.get("fingerprint")): item for item in proposals}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in requested:
        match: dict[str, Any] | None = None
        if isinstance(raw, str):
            match = by_id.get(raw) or by_fingerprint.get(raw)
        elif isinstance(raw, dict):
            if raw.get("id"):
                match = by_id.get(str(raw.get("id")))
            if match is None and raw.get("fingerprint"):
                match = by_fingerprint.get(str(raw.get("fingerprint")))
        if match is None:
            raise RecordValidationError(
                "record was not proposed in this session",
                code="record_not_proposed",
                details={"record": str(raw)[:120]},
            )
        key = str(match.get("id"))
        if key in seen:
            continue
        seen.add(key)
        selected.append(match)
    return selected


def commit_proposals(
    session: Session,
    *,
    workspace: Path,
    meta: dict[str, Any],
    proposals: list[dict[str, Any]],
    member_id: str,
    timezone: str,
) -> dict[str, Any]:
    existing = existing_external_ids(
        session, {_proposal_eid(meta, proposal) for proposal in proposals}
    )
    created = skipped = failed = 0
    counts: dict[str, int] = {}
    record_ids: list[str] = []
    errors: list[dict[str, Any]] = []

    for index, proposal in enumerate(proposals):
        try:
            eid = _proposal_eid(meta, proposal)
        except Exception:  # noqa: BLE001 - 时间/字段异常归为非法记录
            failed += 1
            errors.append({"index": index, "code": "invalid_record", "message": "record fields are invalid"})
            continue
        if eid in existing:
            skipped += 1
            continue
        try:
            if str(proposal.get("kind")) == "ecg":
                record = _create_ecg(
                    session,
                    workspace=workspace,
                    meta=meta,
                    proposal=proposal,
                    eid=eid,
                    member_id=member_id,
                    timezone=timezone,
                )
            else:
                record = _create_numeric(
                    session,
                    meta=meta,
                    proposal=proposal,
                    eid=eid,
                    member_id=member_id,
                    timezone=timezone,
                )
        except InvalidInputError as exc:
            session.rollback()
            failed += 1
            errors.append({"index": index, "code": exc.code, "message": exc.message})
            continue
        except RecordValidationError as exc:
            session.rollback()
            failed += 1
            errors.append({"index": index, "code": exc.code, "message": exc.message})
            continue
        except Exception:
            session.rollback()
            logger.warning("import-agent commit failed index=%s", index, exc_info=True)
            failed += 1
            errors.append({"index": index, "code": "record_failed", "message": "record could not be written"})
            continue
        existing.add(eid)
        created += 1
        kind = str(proposal.get("kind"))
        counts[kind] = counts.get(kind, 0) + 1
        if len(record_ids) < 100:
            record_ids.append(record.id)

    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "counts": counts,
        "recordIds": record_ids,
        "errors": errors[:50],
    }


__all__ = [
    "commit_proposals",
    "existing_external_ids",
    "load_waveform",
    "select_proposals",
]

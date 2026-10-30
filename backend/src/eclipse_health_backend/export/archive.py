"""备份包构造器：ZIP / JSON / CSV。

设计约束（Schema §15、B4-04）：

- ZIP 是唯一可完整恢复的格式；波形与报告按原文件流式写入，避免整包进内存；
- JSON 不内嵌波形，只给出 ``sha256`` 与相对引用，并在 ``signalPolicy`` 里说明；
- CSV 是扁平表，不含波形；
- 备份包内所有路径都由本模块生成，绝不使用用户输入做文件名。
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..analysis.ids import rfc3339
from ..db.models import (
    AnalysisTable,
    MemberTable,
    RecordTable,
    ReportTable,
    SignalTable,
)
from ..db.repositories import record_from_row, signal_from_row
from ..domain.common import utc_now
from ..settings import get_settings

BACKUP_FORMAT = "eclipse-health-backup"
BACKUP_VERSION = 1
TEXT_COMPRESS = zipfile.ZIP_DEFLATED


@contextmanager
def _temp_path(suffix: str) -> Iterator[Path]:
    fd, name = tempfile.mkstemp(prefix="eh-backup-", suffix=suffix)
    os.close(fd)
    path = Path(name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iter_array(handle: io.TextIOBase, items: Iterator[Any]) -> None:
    handle.write("[")
    first = True
    for item in items:
        if not first:
            handle.write(",")
        handle.write(_json_line(item))
        first = False
    handle.write("]")


def _write_json_array_file(path: Path, items: Iterator[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        _iter_array(handle, items)


def _record_items(session: Session) -> Iterator[dict[str, Any]]:
    rows = session.exec(
        select(RecordTable).order_by(RecordTable.captured_at, RecordTable.id)
    ).all()
    for row in rows:
        yield record_from_row(row).model_dump(by_alias=True, mode="json")


def _signal_items(session: Session) -> Iterator[dict[str, Any]]:
    rows = session.exec(
        select(SignalTable).order_by(SignalTable.created_at, SignalTable.id)
    ).all()
    for row in rows:
        yield signal_from_row(row).model_dump(by_alias=True, mode="json")


def _analysis_items(session: Session) -> Iterator[dict[str, Any]]:
    rows = session.exec(
        select(AnalysisTable).order_by(AnalysisTable.created_at, AnalysisTable.id)
    ).all()
    for row in rows:
        data = dict(row.data or {})
        data["id"] = row.id
        data["recordId"] = row.record_id
        data["status"] = row.status
        yield data


def _report_items(session: Session) -> Iterator[dict[str, Any]]:
    rows = session.exec(
        select(ReportTable).order_by(ReportTable.created_at, ReportTable.id)
    ).all()
    for row in rows:
        data = dict(row.data or {})
        data["id"] = row.id
        data["recordId"] = row.record_id
        data["analysisId"] = row.analysis_id
        data["format"] = row.format
        yield data


def _counts(session: Session) -> dict[str, int]:
    return {
        "members": len(session.exec(select(MemberTable.id)).all()),
        "records": len(session.exec(select(RecordTable.id)).all()),
        "signals": len(session.exec(select(SignalTable.id)).all()),
        "analyses": len(session.exec(select(AnalysisTable.id)).all()),
        "measurements": _count_measurements(session),
        "annotations": _count_annotations(session),
        "reports": len(session.exec(select(ReportTable.id)).all()),
    }


def _count_measurements(session: Session) -> int:
    from sqlalchemy import func

    from ..db.models import MeasurementTable

    return int(session.scalar(select(func.count()).select_from(MeasurementTable)) or 0)


def _count_annotations(session: Session) -> int:
    from sqlalchemy import func

    from ..db.models import AnnotationTable

    return int(session.scalar(select(func.count()).select_from(AnnotationTable)) or 0)


def _add_text_file(zf: zipfile.ZipFile, arcname: str, path: Path) -> dict[str, Any]:
    digest = _sha_file(path)
    size = path.stat().st_size
    zf.write(path, arcname, compress_type=TEXT_COMPRESS)
    return {"sha256": digest, "size": size}


def _add_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes) -> dict[str, Any]:
    import hashlib

    zf.writestr(
        zipfile.ZipInfo(arcname),
        data,
        compress_type=TEXT_COMPRESS,
    )
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _add_binary_file(zf: zipfile.ZipFile, arcname: str, path: Path) -> dict[str, Any]:
    """流式写入并同时计算哈希；ZIP 默认 STORED，避免对 float32 做无谓压缩。"""
    import hashlib

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as src, zf.open(arcname, "w", force_zip64=True) as dest:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            dest.write(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def _sha_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _measurements_csv(session: Session, path: Path) -> None:
    from ..db.models import MeasurementTable

    rows = session.exec(
        select(MeasurementTable).order_by(
            MeasurementTable.record_id, MeasurementTable.code, MeasurementTable.id
        )
    ).all()
    columns = [
        "measurementId",
        "recordId",
        "analysisId",
        "code",
        "label",
        "value",
        "unit",
        "ucum",
        "method",
        "confidence",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            data = row.data or {}
            writer.writerow(
                [
                    row.id,
                    row.record_id,
                    row.analysis_id or "",
                    row.code,
                    data.get("label", ""),
                    "" if row.value is None else row.value,
                    row.unit or "",
                    data.get("ucum", ""),
                    data.get("method", ""),
                    data.get("confidence", ""),
                ]
            )


def _records_csv(session: Session, path: Path) -> None:
    columns = [
        "recordId",
        "memberId",
        "recordType",
        "moduleId",
        "capturedAt",
        "timezone",
        "sourceKind",
        "manufacturer",
        "device",
        "leads",
        "samplingRate",
        "durationSec",
        "unit",
        "tags",
        "notes",
        "deletedAt",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for item in _record_items(session):
            source = item.get("source") or {}
            writer.writerow(
                [
                    item.get("id", ""),
                    item.get("memberId", ""),
                    item.get("recordType", ""),
                    item.get("moduleId") or "",
                    item.get("capturedAt", ""),
                    item.get("timezone", ""),
                    source.get("kind", ""),
                    source.get("manufacturer") or "",
                    source.get("device") or "",
                    " ".join(item.get("leads") or []),
                    item.get("samplingRate", ""),
                    item.get("durationSec", ""),
                    item.get("unit", ""),
                    " ".join(item.get("tags") or []),
                    item.get("notes", ""),
                    item.get("deletedAt") or "",
                ]
            )


def build_backup_zip(session: Session) -> Path:
    """构造完整备份 ZIP，返回临时文件路径；调用方负责删除。"""
    settings = get_settings()
    settings.ensure_dirs()
    counts = _counts(session)
    files: dict[str, dict[str, Any]] = {}

    with _temp_path(".zip") as archive_path:
        # 先把大的 JSON 文本写到临时文件，避免 records.json 整包进内存。
        with _temp_path(".json") as records_tmp, _temp_path(".json") as signals_tmp:
            _write_json_array_file(records_tmp, _record_items(session))
            _write_json_array_file(signals_tmp, _signal_items(session))

            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True
            ) as zf:
                files["records.json"] = _add_text_file(zf, "records.json", records_tmp)
                files["signals.json"] = _add_text_file(zf, "signals.json", signals_tmp)

                with _temp_path(".csv") as measurements_tmp:
                    _measurements_csv(session, measurements_tmp)
                    files["measurements.csv"] = _add_text_file(
                        zf, "measurements.csv", measurements_tmp
                    )
                with _temp_path(".csv") as records_csv_tmp:
                    _records_csv(session, records_csv_tmp)
                    files["records.csv"] = _add_text_file(
                        zf, "records.csv", records_csv_tmp
                    )

                for data in _analysis_items(session):
                    analysis_id = str(data.get("id") or "")
                    if not analysis_id:
                        continue
                    arcname = f"analyses/{analysis_id}.json"
                    files[arcname] = _add_bytes(
                        zf, arcname, _json_line(data).encode("utf-8")
                    )

                report_meta: list[dict[str, Any]] = []
                for data in _report_items(session):
                    report_meta.append(data)
                    report_id = str(data.get("id") or "")
                    report_format = str(data.get("format") or "")
                    if not report_id or report_format not in {"pdf", "png"}:
                        continue
                    rel = str((data.get("storage") or {}).get("relativePath") or "")
                    source = settings.data_dir / rel
                    arcname = f"reports/{report_id}.{report_format}"
                    if not source.is_file():
                        continue
                    entry = _add_binary_file(zf, arcname, source)
                    expected = str((data.get("storage") or {}).get("sha256") or "")
                    if expected and entry["sha256"] != expected:
                        from ..domain.errors import StorageIntegrityError

                        raise StorageIntegrityError(
                            "report file checksum mismatch during backup",
                            details={"reportId": report_id},
                        )
                    files[arcname] = entry
                files["reports.json"] = _add_bytes(
                    zf,
                    "reports.json",
                    _json_line(report_meta).encode("utf-8"),
                )

                for row in session.exec(select(SignalTable)):
                    rel = row.relative_path
                    source = settings.data_dir / rel
                    arcname = f"signals/{row.id}.f32"
                    if not source.is_file():
                        # 备份宁可失败也不静默丢失波形。
                        from ..domain.errors import StorageIntegrityError

                        raise StorageIntegrityError(
                            "signal file missing during backup",
                            details={"signalId": row.id},
                        )
                    entry = _add_binary_file(zf, arcname, source)
                    if entry["sha256"] != row.sha256:
                        from ..domain.errors import StorageIntegrityError

                        raise StorageIntegrityError(
                            "signal file checksum mismatch during backup",
                            details={"signalId": row.id},
                        )
                    files[arcname] = entry

                manifest = {
                    "format": BACKUP_FORMAT,
                    "version": BACKUP_VERSION,
                    "createdAt": rfc3339(utc_now()),
                    "app": {"name": "eclipse health", "version": settings.version},
                    "counts": counts,
                    "files": files,
                }
                _add_bytes(
                    zf,
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                )

        final_fd, final_name = tempfile.mkstemp(prefix="eh-backup-", suffix=".zip")
        os.close(final_fd)
        final_path = Path(final_name)
        os.replace(archive_path, final_path)
        return final_path


def backup_file_name(extension: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"eclipse-health-backup-{stamp}.{extension}"


def build_backup_json(session: Session) -> Path:
    """单文件 JSON 快照；波形只保留引用与 sha256，不内嵌 base64。"""
    settings = get_settings()
    fd, name = tempfile.mkstemp(prefix="eh-backup-", suffix=".json")
    os.close(fd)
    path = Path(name)
    header = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "createdAt": rfc3339(utc_now()),
        "app": {"name": "eclipse health", "version": settings.version},
        "signalPolicy": "waveform bytes are not embedded; signals are referenced by relativePath+sha256",
        "counts": _counts(session),
    }
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("{")
            first = True
            for key, value in header.items():
                if not first:
                    handle.write(",")
                handle.write(f"{_json_line(key)}:{_json_line(value)}")
                first = False
            for key, items in (
                ("records", _record_items(session)),
                ("signals", _signal_items(session)),
                ("analyses", _analysis_items(session)),
                ("measurements", _measurement_items(session)),
                ("reports", _report_items(session)),
            ):
                handle.write(f",{_json_line(key)}:")
                _iter_array(handle, items)
            handle.write("}")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _measurement_items(session: Session) -> Iterator[dict[str, Any]]:
    from ..db.models import MeasurementTable

    rows = session.exec(
        select(MeasurementTable).order_by(
            MeasurementTable.record_id, MeasurementTable.analysis_id, MeasurementTable.code
        )
    ).all()
    for row in rows:
        yield dict(row.data or {})


def _measurement_rows(session: Session) -> Iterator[tuple[str, dict[str, Any]]]:
    for data in _measurement_items(session):
        yield str(data.get("recordId") or ""), data


def build_backup_csv(session: Session) -> Path:
    """单文件扁平表：每条记录 × 每个测量值一行；无测量时仍保留记录行。"""
    fd, name = tempfile.mkstemp(prefix="eh-backup-", suffix=".csv")
    os.close(fd)
    path = Path(name)
    measurements_by_record: dict[str, list[dict[str, Any]]] = {}
    for record_id, data in _measurement_rows(session):
        measurements_by_record.setdefault(record_id, []).append(data)

    columns = [
        "recordId",
        "memberId",
        "recordType",
        "moduleId",
        "capturedAt",
        "timezone",
        "sourceKind",
        "manufacturer",
        "device",
        "leads",
        "samplingRate",
        "durationSec",
        "unit",
        "tags",
        "deletedAt",
        "analysisId",
        "measurementCode",
        "measurementLabel",
        "measurementValue",
        "measurementUnit",
        "measurementUcum",
    ]
    try:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for item in _record_items(session):
                source = item.get("source") or {}
                base = [
                    item.get("id", ""),
                    item.get("memberId", ""),
                    item.get("recordType", ""),
                    item.get("moduleId") or "",
                    item.get("capturedAt", ""),
                    item.get("timezone", ""),
                    source.get("kind", ""),
                    source.get("manufacturer") or "",
                    source.get("device") or "",
                    " ".join(item.get("leads") or []),
                    item.get("samplingRate", ""),
                    item.get("durationSec", ""),
                    item.get("unit", ""),
                    " ".join(item.get("tags") or []),
                    item.get("deletedAt") or "",
                ]
                measurements = measurements_by_record.get(str(item.get("id")), [])
                if not measurements:
                    writer.writerow(base + ["", "", "", "", "", ""])
                    continue
                for measurement in measurements:
                    writer.writerow(
                        base
                        + [
                            measurement.get("analysisId", ""),
                            measurement.get("code", ""),
                            measurement.get("label", ""),
                            "" if measurement.get("value") is None else measurement.get("value"),
                            measurement.get("unit", ""),
                            measurement.get("ucum", ""),
                        ]
                    )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


__all__ = [
    "BACKUP_FORMAT",
    "BACKUP_VERSION",
    "backup_file_name",
    "build_backup_csv",
    "build_backup_json",
    "build_backup_zip",
]

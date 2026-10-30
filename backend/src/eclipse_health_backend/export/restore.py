"""从 ZIP 备份恢复数据。

策略（B4-04）：

- 只接受本应用生成的 ``eclipse-health-backup`` ZIP；
- 恢复前自动把当前库备份到 ``data/backups/pre-restore-*.zip``；
- 所有记录/信号/分析/测量/报告都以 **新 ID** 导入，不覆盖现有数据；
- 成员不导入：记录尽量沿用原 ``memberId``，找不到时归到当前默认成员；
- manifest、文件哈希、版本与 ZIP 路径全部校验，损坏返回 422。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..db.models import (
    AnalysisTable,
    AnnotationTable,
    MeasurementTable,
    MemberTable,
    ReportTable,
)
from ..db.repositories import add_record, add_signal, ensure_default_member
from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import InvalidInputError
from ..domain.ids import new_id
from ..domain.models import HealthRecord, Signal
from ..settings import get_settings
from ..storage.files import write_report
from .archive import BACKUP_FORMAT, BACKUP_VERSION, build_backup_zip

MAX_ENTRIES = 200_000
TEXT_ENTRY_LIMIT = 256 * 1024 * 1024
TOP_LEVEL_FILES = {
    "manifest.json",
    "records.json",
    "signals.json",
    "reports.json",
    "measurements.csv",
    "records.csv",
}
_PATH_RE = re.compile(r"^(signals|analyses|reports)/[A-Za-z0-9_.-]{1,160}$")


def _invalid(message: str, code: str = "invalid_backup", **details: Any) -> InvalidInputError:
    return InvalidInputError(message, code=code, details=details)


def _safe_entry_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        return False
    if name in TOP_LEVEL_FILES:
        return True
    return bool(_PATH_RE.match(name))


def _sha_entry(zf: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with zf.open(name) as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _load_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise _invalid("backup is missing manifest.json") from exc
    except zipfile.BadZipFile as exc:
        raise _invalid("backup archive is corrupted", code="backup_corrupted") from exc
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid("manifest.json is not valid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
        raise _invalid("not an eclipse health backup")
    version = manifest.get("version")
    if not isinstance(version, int) or version < 1:
        raise _invalid("backup version is invalid")
    if version > BACKUP_VERSION:
        raise _invalid(
            "backup was created by a newer version of the app",
            code="backup_incompatible_version",
            supported=BACKUP_VERSION,
            found=version,
        )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise _invalid("manifest is missing file hashes")
    return manifest


def _validate_archive(
    zf: zipfile.ZipFile, manifest: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    settings = get_settings()
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise _invalid("backup contains too many entries")
    total = 0
    per_file_limit = settings.signal_max_bytes + 4 * 1024 * 1024
    names: set[str] = set()
    for info in infos:
        if info.is_dir():
            continue
        if not _safe_entry_name(info.filename):
            raise _invalid("backup contains an unsafe path", entries=[info.filename])
        if info.flag_bits & 0x1:
            raise _invalid("encrypted backups are not supported")
        if info.file_size > per_file_limit:
            raise _invalid("backup entry is too large", entries=[info.filename])
        if not info.filename.startswith("signals/") and info.file_size > TEXT_ENTRY_LIMIT:
            raise _invalid("backup text entry is too large", entries=[info.filename])
        total += info.file_size
        names.add(info.filename)
    if total > settings.signal_max_bytes * 4:
        raise _invalid("backup is too large")

    files = manifest["files"]
    if len(files) > MAX_ENTRIES:
        raise _invalid("manifest contains too many entries")
    listed = set(files)
    unexpected = names - listed - {"manifest.json"}
    if unexpected:
        raise _invalid("backup contains files not declared in manifest", entries=sorted(unexpected))

    cleaned: dict[str, dict[str, Any]] = {}
    for name, meta in files.items():
        if not isinstance(name, str) or not _safe_entry_name(name):
            raise _invalid("manifest references an unsafe path")
        if not isinstance(meta, dict):
            raise _invalid("manifest file entry is invalid", entries=[name])
        if name not in names:
            raise _invalid("backup is missing a declared file", entries=[name])
        expected = str(meta.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise _invalid("manifest file hash is invalid", entries=[name])
        actual = _sha_entry(zf, name)
        if actual != expected:
            raise _invalid(
                "backup file checksum mismatch",
                code="backup_corrupted",
                entries=[name],
            )
        cleaned[name] = meta

    if "records.json" not in cleaned:
        raise _invalid("backup is missing records.json")
    if "signals.json" not in cleaned:
        raise _invalid("backup is missing signals.json")
    return cleaned


def _load_json_array(zf: zipfile.ZipFile, name: str) -> list[Any]:
    try:
        value = json.loads(zf.read(name))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid(f"{name} is not valid JSON", code="backup_corrupted") from exc
    if not isinstance(value, list):
        raise _invalid(f"{name} must contain an array")
    return value


def _extract_signal(zf: zipfile.ZipFile, name: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out, zf.open(name) as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def _auto_backup(session: Session) -> str:
    settings = get_settings()
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    temp = build_backup_zip(session)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"pre-restore-{stamp}.zip"
    try:
        shutil.copyfile(temp, backup_dir / name)
    finally:
        temp.unlink(missing_ok=True)
    return name


def _insert_records(
    session: Session,
    raw_records: list[Any],
    record_map: dict[str, str],
    signal_map: dict[str, str],
    member_ids: set[str],
    default_member_id: str,
) -> int:
    inserted = 0
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise _invalid("backup contains an invalid record", index=index)
        old_id = raw["id"]
        if old_id not in record_map:
            continue
        data = dict(raw)
        data["id"] = record_map[old_id]
        member_id = data.get("memberId")
        data["memberId"] = member_id if member_id in member_ids else default_member_id
        data["signalIds"] = [
            signal_map[item] for item in (data.get("signalIds") or []) if item in signal_map
        ]
        try:
            record = HealthRecord.model_validate(data)
        except ValueError as exc:
            raise _invalid(
                "backup contains an invalid record",
                code="backup_invalid_record",
                index=index,
                reason=str(exc)[:300],
            ) from exc
        add_record(session, record, commit=False)
        inserted += 1
    return inserted


def _insert_signals(
    zf: zipfile.ZipFile,
    session: Session,
    raw_signals: list[Any],
    record_map: dict[str, str],
    signal_map: dict[str, str],
    files: dict[str, dict[str, Any]],
    written: list[Path],
) -> int:
    settings = get_settings()
    inserted = 0
    for raw in raw_signals:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        old_id = raw["id"]
        new_id_value = signal_map.get(old_id)
        if new_id_value is None:
            continue
        entry = f"signals/{old_id}.f32"
        if entry not in files:
            continue
        data = dict(raw)
        data["id"] = new_id_value
        data["recordId"] = record_map[str(data.get("recordId"))]
        storage = dict(data.get("storage") or {})
        relative_path = f"signals/{new_id_value}.f32"
        dest = settings.signals_dir / f"{new_id_value}.f32"
        sha256 = _extract_signal(zf, entry, dest)
        written.append(dest)
        storage.update(
            {
                "kind": "file",
                "relativePath": relative_path,
                "sha256": sha256,
                "byteOrder": "little",
            }
        )
        data["storage"] = storage
        try:
            signal = Signal.model_validate(data)
        except ValueError as exc:
            raise _invalid(
                "backup contains an invalid signal",
                code="backup_invalid_signal",
                reason=str(exc)[:300],
            ) from exc
        add_signal(session, signal, commit=False)
        inserted += 1
    return inserted


def _rewrite_children(
    items: Any, *, record_id: str, analysis_id: str, id_kind: str
) -> tuple[list[dict[str, Any]], list[tuple[str, dict[str, Any]]]]:
    rewritten: list[dict[str, Any]] = []
    inserted: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(items, list):
        return rewritten, inserted
    for item in items:
        if not isinstance(item, dict):
            continue
        child_id = new_id(id_kind)
        payload = dict(item)
        payload["id"] = child_id
        payload["recordId"] = record_id
        payload["analysisId"] = analysis_id
        rewritten.append(payload)
        inserted.append((child_id, payload))
    return rewritten, inserted


def _insert_analyses(
    session: Session,
    raw_analyses: list[Any],
    record_map: dict[str, str],
) -> tuple[int, int, int, dict[str, str]]:
    analyses = 0
    measurements = 0
    annotations = 0
    analysis_map: dict[str, str] = {}
    for raw in raw_analyses:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        old_record_id = raw.get("recordId")
        if old_record_id not in record_map:
            continue
        new_record_id = record_map[old_record_id]
        new_analysis_id = new_id("analysis")
        data = dict(raw)
        data["id"] = new_analysis_id
        data["recordId"] = new_record_id
        status = str(data.get("status") or "completed")
        if status in {"queued", "running"}:
            # 备份里的任务无法在恢复后继续执行，标成失败而不是永远排队。
            status = "failed"
        data["status"] = status
        if data.get("beatsRef"):
            data["beatsRef"] = None
        created_at = _parse_dt(data.get("createdAt")) or utc_now()

        measurement_items, measurement_rows = _rewrite_children(
            data.get("measurements"),
            record_id=new_record_id,
            analysis_id=new_analysis_id,
            id_kind="measurement",
        )
        data["measurements"] = measurement_items
        annotation_items, annotation_rows = _rewrite_children(
            data.get("annotations"),
            record_id=new_record_id,
            analysis_id=new_analysis_id,
            id_kind="annotation",
        )
        data["annotations"] = annotation_items

        row = AnalysisTable(
            id=new_analysis_id,
            record_id=new_record_id,
            module_id=data.get("moduleId"),
            model_id=data.get("modelId"),
            status=status,
            data=data,
            created_at=to_storage_dt(created_at),
        )
        session.add(row)
        session.flush()

        for measurement_id, payload in measurement_rows:
            session.add(
                MeasurementTable(
                    id=measurement_id,
                    record_id=new_record_id,
                    analysis_id=new_analysis_id,
                    code=str(payload.get("code") or "unknown"),
                    value=payload.get("value"),
                    unit=payload.get("unit"),
                    data=payload,
                    created_at=utc_now(),
                )
            )
            measurements += 1
        for annotation_id, payload in annotation_rows:
            session.add(
                AnnotationTable(
                    id=annotation_id,
                    record_id=new_record_id,
                    analysis_id=new_analysis_id,
                    type=str(payload.get("type") or "event"),
                    label=payload.get("label"),
                    data=payload,
                    created_at=utc_now(),
                )
            )
            annotations += 1
        analysis_map[raw["id"]] = new_analysis_id
        analyses += 1
    return analyses, measurements, annotations, analysis_map


def _insert_reports(
    zf: zipfile.ZipFile,
    session: Session,
    raw_reports: list[Any],
    record_map: dict[str, str],
    analysis_map: dict[str, str],
    files: dict[str, dict[str, Any]],
    written: list[Path],
) -> int:
    inserted = 0
    for raw in raw_reports:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        old_record_id = raw.get("recordId")
        if old_record_id not in record_map:
            continue
        report_format = str(raw.get("format") or "")
        if report_format not in {"pdf", "png"}:
            continue
        entry = f"reports/{raw['id']}.{report_format}"
        if entry not in files:
            continue
        new_report_id = new_id("report")
        new_record_id = record_map[old_record_id]
        new_analysis_id = analysis_map.get(str(raw.get("analysisId") or ""))
        data = zf.read(entry)
        relative_path, sha256, size = write_report(new_report_id, report_format, data)
        written.append(get_settings().reports_dir / f"{new_report_id}.{report_format}")
        payload = dict(raw)
        payload["id"] = new_report_id
        payload["recordId"] = new_record_id
        payload["analysisId"] = new_analysis_id
        payload["format"] = report_format
        payload["storage"] = {
            "relativePath": relative_path,
            "sha256": sha256,
            "size": size,
        }
        created_at = _parse_dt(payload.get("createdAt")) or utc_now()
        session.add(
            ReportTable(
                id=new_report_id,
                record_id=new_record_id,
                analysis_id=new_analysis_id,
                format=report_format,
                data=payload,
                created_at=to_storage_dt(created_at),
            )
        )
        inserted += 1
    return inserted


def restore_backup_zip(archive_path: Path, session: Session) -> dict[str, Any]:
    """恢复 ZIP 备份；返回导入统计与自动备份文件名。"""
    try:
        zf = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _invalid("backup archive is corrupted", code="backup_corrupted") from exc

    written: list[Path] = []
    with zf:
        manifest = _load_manifest(zf)
        files = _validate_archive(zf, manifest)

        raw_records = _load_json_array(zf, "records.json")
        raw_signals = _load_json_array(zf, "signals.json")
        raw_reports = (
            _load_json_array(zf, "reports.json") if "reports.json" in files else []
        )
        raw_analyses: list[Any] = []
        for name in sorted(files):
            if not (name.startswith("analyses/") and name.endswith(".json")):
                continue
            try:
                raw_analyses.append(json.loads(zf.read(name)))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _invalid(
                    "backup analysis is not valid JSON",
                    code="backup_corrupted",
                    entries=[name],
                ) from exc

        record_map = {
            raw["id"]: new_id("record")
            for raw in raw_records
            if isinstance(raw, dict) and isinstance(raw.get("id"), str)
        }
        signal_map = {
            raw["id"]: new_id("signal")
            for raw in raw_signals
            if isinstance(raw, dict)
            and isinstance(raw.get("id"), str)
            and raw.get("recordId") in record_map
            and f"signals/{raw['id']}.f32" in files
        }

        auto_backup = _auto_backup(session)
        member_ids = {str(item) for item in session.exec(select(MemberTable.id)).all()}
        default_member_id = ensure_default_member(session).id

        try:
            records = _insert_records(
                session,
                raw_records,
                record_map,
                signal_map,
                member_ids,
                default_member_id,
            )
            session.flush()
            signals = _insert_signals(
                zf, session, raw_signals, record_map, signal_map, files, written
            )
            analyses, measurements, annotations, analysis_map = _insert_analyses(
                session, raw_analyses, record_map
            )
            reports = _insert_reports(
                zf, session, raw_reports, record_map, analysis_map, files, written
            )
            session.commit()
        except Exception:
            session.rollback()
            for path in written:
                path.unlink(missing_ok=True)
            raise

    return {
        "backupVersion": int(manifest.get("version") or BACKUP_VERSION),
        "createdAt": manifest.get("createdAt"),
        "autoBackup": auto_backup,
        "imported": {
            "records": records,
            "signals": signals,
            "analyses": analyses,
            "measurements": measurements,
            "annotations": annotations,
            "reports": reports,
        },
        "skipped": {
            "records": len(raw_records) - records,
            "signals": len(raw_signals) - signals,
            "analyses": len(raw_analyses) - analyses,
            "reports": len(raw_reports) - reports,
        },
    }


__all__ = ["MAX_ENTRIES", "restore_backup_zip"]

"""存储统计与「清空全部数据」。

清空范围：记录、波形、分析、测量、标注、报告；保留成员、设置与只追加审计。
审计只记录数量，不记录任何健康数据内容。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func
from sqlmodel import Session, select

from ..db.models import (
    AnalysisTable,
    AnnotationTable,
    MeasurementTable,
    MemberTable,
    RecordTable,
    ReportTable,
    SignalTable,
)
from ..settings import get_settings

logger = logging.getLogger(__name__)

CORE_MODELS = {
    "members": MemberTable,
    "records": RecordTable,
    "signals": SignalTable,
    "analyses": AnalysisTable,
    "measurements": MeasurementTable,
    "annotations": AnnotationTable,
    "reports": ReportTable,
}

# 清空顺序：子表在前，避免外键约束。
PURGE_ORDER = (
    MeasurementTable,
    AnnotationTable,
    ReportTable,
    AnalysisTable,
    SignalTable,
    RecordTable,
)


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _dir_bytes(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
    except OSError:
        return total
    return total


def _database_bytes() -> int:
    settings = get_settings()
    total = 0
    for candidate in (
        settings.db_path,
        settings.db_path.with_name(settings.db_path.name + "-wal"),
        settings.db_path.with_name(settings.db_path.name + "-shm"),
    ):
        try:
            total += candidate.stat().st_size
        except OSError:
            continue
    return total


def storage_info(session: Session) -> dict[str, Any]:
    settings = get_settings()
    counts = {name: _count(session, model) for name, model in CORE_MODELS.items()}
    counts["deletedRecords"] = int(
        session.scalar(
            select(func.count())
            .select_from(RecordTable)
            .where(RecordTable.deleted_at.is_not(None))
        )
        or 0
    )
    signals_bytes = _dir_bytes(settings.signals_dir)
    reports_bytes = _dir_bytes(settings.reports_dir)
    imports_bytes = _dir_bytes(settings.imports_dir)
    database_bytes = _database_bytes()
    return {
        "dataDir": str(settings.data_dir),
        "counts": counts,
        "bytes": {
            "signals": signals_bytes,
            "reports": reports_bytes,
            "imports": imports_bytes,
            "database": database_bytes,
            "total": signals_bytes + reports_bytes + imports_bytes + database_bytes,
        },
        "localOnly": True,
        "telemetry": False,
    }


def _write_audit(session: Session, counts: dict[str, int]) -> None:
    try:
        from ..modules import audit
    except Exception:  # noqa: BLE001 - 模块系统缺失时审计不可用，但不能阻断清空
        logger.info("audit module unavailable; privacy purge is not audited")
        return
    try:
        audit.append(
            session,
            "privacy.purge",
            scope="all",
            detail={"counts": counts},
        )
    except Exception:
        logger.exception("failed to append privacy audit event")


def _clear_directory(path: Path) -> int:
    removed = 0
    if not path.is_dir():
        return removed
    for child in path.iterdir():
        if not child.is_file():
            continue
        try:
            child.unlink()
            removed += 1
        except OSError:
            logger.warning("failed to remove data file during purge", exc_info=True)
    return removed


def purge_all(session: Session) -> dict[str, Any]:
    counts = {name: _count(session, model) for name, model in CORE_MODELS.items()}
    _write_audit(session, counts)
    # 成员属于配置而不是健康数据，保留；返回体里也不声称删除了成员。
    counts.pop("members", None)
    for model in PURGE_ORDER:
        session.execute(delete(model))
    session.commit()

    settings = get_settings()
    removed = {
        "signals": _clear_directory(settings.signals_dir),
        "reports": _clear_directory(settings.reports_dir),
        "imports": _clear_directory(settings.imports_dir),
    }
    logger.info("privacy purge completed records=%s", counts.get("records"))
    return {"deleted": counts, "removedFiles": removed}


__all__ = ["CORE_MODELS", "PURGE_ORDER", "purge_all", "storage_info"]

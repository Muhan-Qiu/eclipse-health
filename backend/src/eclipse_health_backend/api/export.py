"""导出/备份 API（D5）。

- ``GET /export/backup?format=zip|json|csv``：下载备份；
- ``POST /import/backup``：上传 ZIP 恢复，恢复前自动备份当前库。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..domain.errors import InvalidInputError
from ..export import (
    build_backup_csv,
    build_backup_json,
    build_backup_zip,
    restore_backup_zip,
)
from ..export.archive import backup_file_name
from ..settings import get_settings
from .deps import SessionDep

router = APIRouter(tags=["export"])

BackupFormat = Literal["zip", "json", "csv"]
MEDIA_TYPES = {
    "zip": "application/zip",
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
}
_CHUNK = 1024 * 1024


class RestoreCounts(BaseModel):
    records: int = 0
    signals: int = 0
    analyses: int = 0
    measurements: int = 0
    annotations: int = 0
    reports: int = 0


class RestoreSkipped(BaseModel):
    records: int = 0
    signals: int = 0
    analyses: int = 0
    reports: int = 0


class RestoreResponse(BaseModel):
    backupVersion: int
    createdAt: str | None = None
    autoBackup: str
    imported: RestoreCounts
    skipped: RestoreSkipped


def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get(
    "/export/backup",
    summary="导出备份（ZIP / JSON / CSV）",
    responses={200: {"content": {"application/zip": {}, "application/json": {}, "text/csv": {}}}},
)
def download_backup(
    session: SessionDep,
    background: BackgroundTasks,
    format_: Annotated[BackupFormat, Query(alias="format")] = "zip",
) -> FileResponse:
    if format_ == "zip":
        path = build_backup_zip(session)
        filename = backup_file_name("zip")
    elif format_ == "json":
        path = build_backup_json(session)
        filename = backup_file_name("json")
    else:
        path = build_backup_csv(session)
        filename = backup_file_name("csv")
    background.add_task(_cleanup, path)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[format_],
        filename=filename,
        headers={"Cache-Control": "no-store", "X-Backup-Format": format_},
    )


def _copy_upload(file: UploadFile, limit: int) -> Path:
    fd, name = tempfile.mkstemp(prefix="eh-restore-", suffix=".zip")
    dest = Path(name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = file.file.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise InvalidInputError(
                        "backup upload is too large",
                        code="backup_too_large",
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        details={"limit": limit},
                    )
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise InvalidInputError("backup upload is empty", code="empty_backup")
    return dest


@router.post(
    "/import/backup",
    response_model=RestoreResponse,
    summary="从 ZIP 备份恢复（新 ID 导入）",
    responses={
        413: {"description": "备份文件过大"},
        422: {"description": "备份损坏、版本不兼容或缺少 manifest"},
    },
)
def import_backup(session: SessionDep, file: Annotated[UploadFile, File()]) -> Any:
    settings = get_settings()
    limit = settings.signal_max_bytes * 4
    path = _copy_upload(file, limit)
    try:
        result = restore_backup_zip(path, session)
    finally:
        path.unlink(missing_ok=True)
    result["imported"] = RestoreCounts(**result["imported"])
    result["skipped"] = RestoreSkipped(**result["skipped"])
    return RestoreResponse(**result)


__all__ = ["router"]

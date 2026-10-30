"""诊断日志 API（H6）：``GET /diagnostics/bundle``。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse

from ..diagnostics.service import build_diagnostics_bundle
from .deps import SessionDep

router = APIRouter(tags=["diagnostics"])


def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get(
    "/diagnostics/bundle",
    summary="下载诊断包（版本、环境、脱敏日志）",
    responses={200: {"content": {"application/zip": {}}}},
)
def download_bundle(session: SessionDep, background: BackgroundTasks) -> FileResponse:
    path = build_diagnostics_bundle(session)
    background.add_task(_cleanup, path)
    return FileResponse(
        path,
        media_type="application/zip",
        filename="eclipse-health-diagnostics.zip",
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["router"]

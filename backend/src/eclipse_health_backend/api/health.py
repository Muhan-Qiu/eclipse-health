"""GET /api/v1/health"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..db.base import applied_migrations
from ..domain.common import utc_now
from ..settings import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    version: str
    startedAt: datetime
    now: datetime
    database: str
    databasePath: str
    dataDir: str
    migrations: list[str]


@router.get("/health", response_model=HealthResponse, summary="服务健康检查")
def health(request: Request) -> Any:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.version,
        startedAt=request.app.state.started_at,
        now=utc_now(),
        database=f"sqlite:///{settings.db_path.as_posix()}",
        databasePath=str(settings.db_path),
        dataDir=str(settings.data_dir),
        migrations=applied_migrations(),
    )

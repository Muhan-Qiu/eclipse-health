"""``/api/v1/marketplace`` 路由；挂载前缀由 ``api/__init__.py`` 负责。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..modules.errors import ModuleError
from .config import MarketplaceConfig
from .errors import MarketplaceError, validate_source
from .index import load_public_keys
from .service import MarketplaceService

router = APIRouter(tags=["marketplace"])

# 依赖安装可能要下载 PyPI 包（首次几分钟），不能让前端 HTTP 超时。
# 异步安装任务只保存在内存；进程重启后任务丢失，前端会重新发起。
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 3600.0


def get_service() -> MarketplaceService:
    # 延迟导入：模块内核的初始化只在真正访问市场时才需要。
    from ..modules.api import get_manager

    return MarketplaceService(get_manager())


def _error(exc: MarketplaceError | ModuleError) -> JSONResponse:
    if isinstance(exc, MarketplaceError):
        return JSONResponse(status_code=exc.http_status, content=exc.to_http_detail())
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "details": exc.detail or None},
    )


class InstallRequest(BaseModel):
    source: str = Field(default="official", max_length=32)
    moduleId: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)


@router.get("/sources")
def list_sources() -> JSONResponse:
    config = MarketplaceConfig.from_env()
    try:
        key_ids = sorted(load_public_keys(config.public_key_path))
    except MarketplaceError:
        key_ids = []
    return JSONResponse(
        content={
            "official": {
                "url": config.official_url,
                "configured": bool(config.official_url),
            },
            "community": {
                "url": config.community_url,
                "configured": bool(config.community_url),
            },
            "keyIds": key_ids,
        }
    )


@router.get("/index")
def list_index(
    source: str = Query(default="official"),
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=64),
) -> JSONResponse:
    try:
        validate_source(source)
        payload = get_service().list_entries(source, query=q, category=category)
        return JSONResponse(content=jsonable_encoder(payload))
    except (MarketplaceError, ModuleError) as exc:
        return _error(exc)


@router.get("/updates")
def list_updates() -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(get_service().updates()))
    except (MarketplaceError, ModuleError) as exc:
        return _error(exc)


def _prune_jobs() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    with _JOBS_LOCK:
        stale = [
            key
            for key, job in _JOBS.items()
            if float(job.get("finishedAt") or job.get("startedAt") or 0) < cutoff
        ]
        for key in stale:
            _JOBS.pop(key, None)


def _run_install_job(job_id: str, request: InstallRequest) -> None:
    try:
        payload = get_service().install(request.source, request.moduleId, request.version)
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is not None:
                job.update(
                    status="done",
                    result=jsonable_encoder(payload),
                    finishedAt=time.time(),
                )
    except (MarketplaceError, ModuleError) as exc:
        body = (
            exc.to_http_detail()
            if isinstance(exc, MarketplaceError)
            else {
                "code": exc.code,
                "message": exc.message,
                "details": exc.detail or None,
            }
        )
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is not None:
                job.update(
                    status="error",
                    error=body,
                    finishedAt=time.time(),
                )
    except Exception as exc:  # noqa: BLE001 - 后台任务不能把异常留给线程
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is not None:
                job.update(
                    status="error",
                    error={
                        "code": "module_install_failed",
                        "message": str(exc)[:300] or type(exc).__name__,
                    },
                    finishedAt=time.time(),
                )


@router.post("/install")
def install_module(
    request: InstallRequest,
    async_mode: bool = Query(default=False, alias="async"),
) -> JSONResponse:
    if not async_mode:
        try:
            payload: dict[str, Any] = get_service().install(
                request.source, request.moduleId, request.version
            )
            return JSONResponse(content=jsonable_encoder(payload))
        except (MarketplaceError, ModuleError) as exc:
            return _error(exc)
    _prune_jobs()
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "jobId": job_id,
            "status": "running",
            "source": request.source,
            "moduleId": request.moduleId,
            "version": request.version,
            "startedAt": time.time(),
            "finishedAt": None,
            "result": None,
            "error": None,
        }
    thread = threading.Thread(
        target=_run_install_job,
        args=(job_id, request),
        name=f"marketplace-install-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return JSONResponse(
        status_code=202,
        content={"jobId": job_id, "status": "running", "moduleId": request.moduleId},
    )


@router.get("/install/{job_id}")
def install_status(job_id: str) -> JSONResponse:
    with _JOBS_LOCK:
        job = dict(_JOBS.get(job_id) or {})
    if not job:
        return JSONResponse(
            status_code=404,
            content={"code": "install_job_not_found", "message": "安装任务不存在或已过期"},
        )
    return JSONResponse(content=jsonable_encoder(job))


__all__ = ["get_service", "router"]

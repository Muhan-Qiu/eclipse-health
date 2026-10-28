"""模块系统 REST 路由。挂载点为 /api/v1/modules（前缀由 app.py 负责）。"""

from __future__ import annotations

import atexit
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from .constants import DEFAULT_LOCALE
from .errors import ModuleError
from .manager import ModuleManager

router = APIRouter(tags=["modules"])

_manager_guard = threading.Lock()
_manager: ModuleManager | None = None


def init_module_system(
    *,
    engine: Engine | None = None,
    data_dir: Path | None = None,
    locale: str = DEFAULT_LOCALE,
) -> ModuleManager:
    """由 B1-01 在启动时调用；也可由 API 首次访问时懒初始化。"""
    global _manager
    with _manager_guard:
        if _manager is not None:
            _manager.shutdown()
        _manager = ModuleManager(data_dir=data_dir, engine=engine, locale=locale)
        return _manager


def get_manager() -> ModuleManager:
    global _manager
    if _manager is None:
        with _manager_guard:
            if _manager is None:
                _manager = ModuleManager()
    return _manager


def shutdown_module_system() -> None:
    global _manager
    with _manager_guard:
        if _manager is not None:
            _manager.shutdown()
            _manager = None


# B1-01 的 app.py 未调用本模块的关闭钩子；进程退出时兜底停掉 worker。
atexit.register(shutdown_module_system)


def _run(action: Callable[[], Any]) -> JSONResponse:
    """业务错误统一为 {code, message, details}，与核心 API 的错误体一致。"""
    try:
        return JSONResponse(content=jsonable_encoder(action()))
    except ModuleError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.detail or None,
            },
        )


class InstallRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    enable: bool = False


class RpcRequest(BaseModel):
    method: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    version: str | None = Field(default=None, max_length=64)


# /audit 必须在 /{module_id} 之前注册，避免被路径参数吞掉。
@router.get("/audit")
def list_audit_events(
    module_id: Annotated[str | None, Query(alias="moduleId")] = None,
    action_: Annotated[str | None, Query(alias="action", max_length=64)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    manager = get_manager()

    def action() -> dict[str, Any]:
        events = manager.audit_events(
            module_id=module_id, action=action_, since=since, until=until, limit=limit, offset=offset
        )
        return {"events": events, "count": len(events)}

    return _run(action)


@router.get("")
def list_modules() -> JSONResponse:
    manager = get_manager()
    return _run(lambda: {"modules": manager.list_modules()})


@router.post("/install")
def install_module(request: InstallRequest) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.install(request.path, enable=request.enable))


@router.get("/{module_id}/permissions")
def get_permissions(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.list_permissions(module_id))


@router.post("/{module_id}/permissions/{scope}")
def grant_permission(module_id: str, scope: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.grant_permission(module_id, scope))


@router.delete("/{module_id}/permissions/{scope}")
def revoke_permission(module_id: str, scope: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.revoke_permission(module_id, scope))


@router.post("/{module_id}/enable")
def enable_module(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.enable(module_id))


@router.post("/{module_id}/disable")
def disable_module(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.disable(module_id))


@router.post("/{module_id}/start")
def start_module(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.start(module_id))


@router.post("/{module_id}/stop")
def stop_module(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.stop(module_id))


@router.post("/{module_id}/rollback")
def rollback_module(module_id: str, request: RollbackRequest) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.rollback(module_id, request.version))


@router.post("/{module_id}/rpc")
def call_module(module_id: str, request: RpcRequest) -> JSONResponse:
    manager = get_manager()
    return _run(
        lambda: {
            "moduleId": module_id,
            "method": request.method,
            "result": manager.call(module_id, request.method, request.params),
        }
    )


@router.get("/{module_id}")
def get_module(module_id: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.get_module(module_id))


@router.delete("/{module_id}")
def uninstall_module(
    module_id: str,
    keep_data: Annotated[bool, Query(alias="keepData")] = True,
) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: manager.uninstall(module_id, keep_data=keep_data))


__all__ = [
    "get_manager",
    "init_module_system",
    "router",
    "shutdown_module_system",
]

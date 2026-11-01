"""模块系统 REST 路由。挂载点为 /api/v1/modules（前缀由 app.py 负责）。"""

from __future__ import annotations

import atexit
import json
import os
import tempfile
import threading
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from . import package
from .constants import DEFAULT_LOCALE, MAX_MANIFEST_BYTES
from .contributions import collect_contributions
from .errors import ModuleError
from .manager import ModuleManager
from .manifest import Manifest, check_compatibility, load_manifest_file, parse_manifest
from .permissions import describe_scope, permission_catalog

router = APIRouter(tags=["modules"])

# 上传入口的独立上限；内核的 MAX_PACKAGE_BYTES 仍会再校验一次。
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

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


def _error_response(exc: ModuleError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.detail or None,
        },
    )


def _run(action: Callable[[], Any]) -> JSONResponse:
    """业务错误统一为 {code, message, details}，与核心 API 的错误体一致。"""
    try:
        return JSONResponse(content=jsonable_encoder(action()))
    except ModuleError as exc:
        return _error_response(exc)


def _permission_details(scopes: list[str]) -> list[dict[str, str]]:
    return [describe_scope(scope) for scope in scopes]


def _with_permission_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """在既有 requested/granted/available 之外补 UI 需要的 scopes 视图。"""
    granted = set(payload.get("granted") or [])
    scopes: list[dict[str, Any]] = []
    for scope in payload.get("requested") or []:
        detail: dict[str, Any] = describe_scope(scope)
        detail["requested"] = True
        detail["granted"] = scope in granted
        scopes.append(detail)
    return {**payload, "scopes": scopes}


def _parse_scope_selection(raw: str | None) -> set[str] | None:
    """接受 JSON 数组或逗号分隔的 scope 列表；None 表示沿用内核默认授权。"""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModuleError("INVALID_INPUT", "permissions 必须是权限数组") from exc
        if not isinstance(parsed, list):
            raise ModuleError("INVALID_INPUT", "permissions 必须是权限数组")
        items: list[Any] = parsed
    else:
        items = text.split(",")
    scopes: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ModuleError("INVALID_INPUT", "permissions 只能包含权限字符串")
        scope = item.strip()
        if scope:
            scopes.add(scope)
    return scopes


def _save_upload(upload: UploadFile) -> Path:
    """把上传流写入临时 .ehmod；只校验扩展名、ZIP 魔数与大小。"""
    filename = (upload.filename or "").strip()
    if not filename.lower().endswith(".ehmod"):
        raise ModuleError("INVALID_INPUT", "需要 .ehmod 文件")
    fd, raw_path = tempfile.mkstemp(prefix="ehmod-upload-", suffix=".ehmod")
    path = Path(raw_path)
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            chunk = upload.file.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                raise ModuleError("INVALID_PACKAGE", "空文件不是合法的模块包")
            if not chunk.startswith(_ZIP_MAGIC):
                raise ModuleError("INVALID_PACKAGE", "不是合法的 ZIP 包")
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise ModuleError(
                    "RESOURCE_EXCEEDED",
                    "模块包超过上传大小上限",
                    {"maxBytes": MAX_UPLOAD_BYTES},
                )
            handle.write(chunk)
            while True:
                chunk = upload.file.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise ModuleError(
                        "RESOURCE_EXCEEDED",
                        "模块包超过上传大小上限",
                        {"maxBytes": MAX_UPLOAD_BYTES},
                    )
                handle.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()
    return path


def _read_package_manifest(path: Path) -> Manifest:
    """只读包内 module.json，用于安装前校验用户勾选的权限。"""
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo("module.json")
            except KeyError as exc:
                raise ModuleError("INVALID_PACKAGE", "模块包缺少 module.json") from exc
            if info.file_size > MAX_MANIFEST_BYTES:
                raise ModuleError("INVALID_PACKAGE", "module.json 超过 1MB 上限")
            raw = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise ModuleError("INVALID_PACKAGE", "不是合法的 ZIP 包") from exc
    except OSError as exc:
        raise ModuleError("INVALID_PACKAGE", "模块包无法读取") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModuleError("INVALID_PACKAGE", "module.json 不是合法 UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ModuleError("INVALID_PACKAGE", "module.json 顶层必须是对象")
    return parse_manifest(data)


def _inspect_package(path: Path, manager: ModuleManager) -> tuple[Manifest, list[str], int]:
    """解压到临时目录做完整预检，随后立即丢弃，不写模块目录。"""
    with tempfile.TemporaryDirectory(prefix="ehmod-inspect-") as tmp:
        staging = Path(tmp) / "package"
        try:
            with zipfile.ZipFile(path) as archive:
                report = package.extract_package(archive, staging)
        except zipfile.BadZipFile as exc:
            raise ModuleError("INVALID_PACKAGE", "不是合法的 ZIP 包") from exc
        except OSError as exc:
            raise ModuleError("INVALID_PACKAGE", "模块包无法读取") from exc
        manifest = load_manifest_file(staging / "module.json")
        check_compatibility(manifest, core_version=manager.core_version)
        package.verify_layout(staging, manifest)
        warnings = package.verify_checksums(staging)
        return manifest, warnings, report.bytes


def _preview_payload(
    manifest: Manifest,
    warnings: list[str],
    package_bytes: int,
    manager: ModuleManager,
) -> dict[str, Any]:
    installed: dict[str, Any] | None = None
    try:
        installed = manager.get_module(manifest.id)
    except ModuleError as exc:
        if exc.code != "MODULE_NOT_FOUND":
            raise
    requested = list(manifest.permissions)
    previous = list(installed["requestedPermissions"]) if installed else requested
    return {
        "id": manifest.id,
        "name": manifest.name,
        "description": manifest.description,
        "version": manifest.version,
        "type": manifest.type.value,
        "author": manifest.author.model_dump(exclude_none=True),
        "license": manifest.license,
        "homepage": manifest.homepage,
        "repository": manifest.repository,
        "apiVersion": manifest.api_version,
        "schemaVersion": manifest.schema_version,
        "engines": manifest.engines.model_dump(),
        "permissions": requested,
        "permissionDetails": _permission_details(requested),
        "contributes": manifest.contributes,
        "resources": manifest.resources.model_dump(by_alias=True, exclude_none=True),
        "updateChannel": manifest.update_channel,
        "warnings": warnings,
        "packageBytes": package_bytes,
        "alreadyInstalled": installed is not None,
        "installedVersion": installed["version"] if installed else None,
        "newPermissions": sorted(set(requested) - set(previous)),
    }


def _apply_scope_selection(
    manager: ModuleManager,
    summary: dict[str, Any],
    manifest: Manifest,
    selected: set[str],
) -> dict[str, Any]:
    """内核安装后会授予全部非高风险 scope；这里按用户勾选补授/撤销。"""
    requested = set(manifest.permissions)
    desired = selected & requested
    granted = set(summary.get("grantedPermissions") or [])
    for scope in sorted(granted - desired):
        manager.revoke_permission(summary["id"], scope)
    for scope in sorted(desired - granted):
        manager.grant_permission(summary["id"], scope)
    updated = manager.get_module(summary["id"])
    updated["warnings"] = list(summary.get("warnings") or [])
    updated["addedPermissions"] = list(summary.get("addedPermissions") or [])
    return updated


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
        return {
            "events": events,
            "count": len(events),
            "limit": limit,
            "offset": offset,
            # 内核按 created_at 倒序；count == limit 时可能还有更早的记录。
            "hasMore": len(events) == limit,
        }

    return _run(action)


@router.get("/permission-catalog")
def list_permission_catalog() -> JSONResponse:
    """全部权限 scope 的风险与说明，供安装确认和权限管理复用。"""
    return JSONResponse(content={"permissions": permission_catalog()})


@router.get("/contributions")
def list_contributions(
    kind: Annotated[
        str | None,
        Query(alias="type", max_length=32, description="widgets|pages|tools|recordTypes"),
    ] = None,
) -> JSONResponse:
    """聚合已安装且启用模块的贡献点；不启动 worker、不执行模块代码。"""
    manager = get_manager()
    return _run(lambda: collect_contributions(manager, kind=kind))


@router.post("/preview-upload")
def preview_upload(
    file: Annotated[UploadFile, File(description=".ehmod 模块包")],
) -> JSONResponse:
    """上传 .ehmod 并返回 manifest 摘要与权限清单；不安装、不落盘到模块目录。

    错误体与安装一致；坏包、校验失败、版本不兼容都会在确认安装前返回。
    """
    manager = get_manager()
    temporary: Path | None = None
    try:
        temporary = _save_upload(file)
        manifest, warnings, package_bytes = _inspect_package(temporary, manager)
        payload = _preview_payload(manifest, warnings, package_bytes, manager)
        return JSONResponse(content=jsonable_encoder(payload))
    except ModuleError as exc:
        return _error_response(exc)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@router.post("/install-upload")
def install_upload(
    file: Annotated[UploadFile, File(description=".ehmod 模块包")],
    enable: Annotated[bool, Form()] = False,
    permissions: Annotated[
        str | None,
        Form(description="已确认的 scope：JSON 数组或逗号分隔；省略则沿用内核默认授权"),
    ] = None,
) -> JSONResponse:
    """上传安装 `.ehmod`，返回与 `POST /modules/install` 相同的模块摘要。

    `permissions` 只允许 manifest 已请求的 scope；高风险 scope 需要调用方显式列出。
    临时文件在安装后立即删除，模块目录只保留解压后的文件。
    """
    manager = get_manager()
    selected = _parse_scope_selection(permissions)
    temporary: Path | None = None
    try:
        temporary = _save_upload(file)
        manifest = _read_package_manifest(temporary)
        if selected is not None:
            unknown = sorted(selected - set(manifest.permissions))
            if unknown:
                raise ModuleError(
                    "INVALID_INPUT",
                    "权限清单包含模块未请求的 scope",
                    {"unknown": unknown},
                )
        summary = manager.install(temporary, enable=enable)
        if selected is not None:
            summary = _apply_scope_selection(manager, summary, manifest, selected)
        return JSONResponse(content=jsonable_encoder(summary))
    except ModuleError as exc:
        return _error_response(exc)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    return _run(lambda: _with_permission_metadata(manager.list_permissions(module_id)))


@router.post("/{module_id}/permissions/{scope}")
def grant_permission(module_id: str, scope: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: _with_permission_metadata(manager.grant_permission(module_id, scope)))


@router.delete("/{module_id}/permissions/{scope}")
def revoke_permission(module_id: str, scope: str) -> JSONResponse:
    manager = get_manager()
    return _run(lambda: _with_permission_metadata(manager.revoke_permission(module_id, scope)))


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


@router.get("/{module_id}/manifest")
def get_module_manifest(module_id: str) -> JSONResponse:
    """已安装模块的 manifest 投影：详情页展示用，不含 entry 相对路径。"""

    def action() -> dict[str, Any]:
        manager = get_manager()
        summary = manager.get_module(module_id)
        path = manager.modules_root / module_id / summary["version"] / "module.json"
        manifest = load_manifest_file(path)
        return {
            "id": manifest.id,
            "name": manifest.name,
            "description": manifest.description,
            "version": manifest.version,
            "type": manifest.type.value,
            "schemaVersion": manifest.schema_version,
            "apiVersion": manifest.api_version,
            "engines": manifest.engines.model_dump(),
            "author": manifest.author.model_dump(exclude_none=True),
            "license": manifest.license,
            "homepage": manifest.homepage,
            "repository": manifest.repository,
            "permissions": list(manifest.permissions),
            "permissionDetails": _permission_details(list(manifest.permissions)),
            "contributes": manifest.contributes,
            "resources": manifest.resources.model_dump(by_alias=True, exclude_none=True),
            "updateChannel": manifest.update_channel,
            "i18n": manifest.i18n,
        }

    return _run(action)


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

"""模块内核门面：安装、启用、启动、调用、权限、审计、卸载。"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from . import audit, package, registry
from .constants import (
    CORE_VERSION,
    DEFAULT_CALL_TIMEOUT_S,
    DEFAULT_LOCALE,
    MAX_AUTOMATIC_RESTARTS,
)
from .db_compat import DatabaseHandles, database_handles, resolve_data_dir
from .errors import ModuleError
from .host import ModuleHost
from .manifest import Manifest, check_compatibility, load_manifest_file
from .permissions import (
    DEFAULT_DENIED_SCOPES,
    check_core_call,
    diff_scopes,
    required_scope,
    validate_scope,
)

_MISSING = object()


class ModuleManager:
    """单进程内的模块内核。所有公开方法线程安全。"""

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        engine: Engine | None = None,
        locale: str = DEFAULT_LOCALE,
        core_version: str = CORE_VERSION,
        call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S,
        max_restarts: int = MAX_AUTOMATIC_RESTARTS,
    ) -> None:
        self.data_dir = (data_dir or resolve_data_dir()).resolve()
        handles: DatabaseHandles = database_handles(self.data_dir)
        self.engine: Engine = engine or handles.engine
        self.metadata = handles.metadata
        self.locale = locale
        self.core_version = core_version
        self.call_timeout_s = call_timeout_s
        self.max_restarts = max_restarts

        self.modules_root = self.data_dir / "modules"
        self.logs_root = self.data_dir / "logs" / "modules"
        self.modules_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

        self._op_lock = threading.RLock()
        self._id_locks_guard = threading.Lock()
        self._id_locks: dict[str, threading.RLock] = {}
        self._hosts: dict[str, ModuleHost] = {}
        self._states: dict[str, str] = {}
        self._crash_counts: dict[str, int] = {}
        self._create_tables()

    # ------------------------------------------------------------------ 基础设施
    def _create_tables(self) -> None:
        for table in (
            registry.InstalledModule.__table__,
            registry.ModulePermission.__table__,
            audit.AuditEvent.__table__,
        ):
            table.create(bind=self.engine, checkfirst=True)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = Session(self.engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _lock_for(self, module_id: str) -> threading.RLock:
        with self._id_locks_guard:
            lock = self._id_locks.get(module_id)
            if lock is None:
                lock = threading.RLock()
                self._id_locks[module_id] = lock
            return lock

    def _require_row(self, session: Session, module_id: str) -> registry.InstalledModule:
        row = registry.get_module(session, module_id)
        if row is None:
            raise ModuleError("MODULE_NOT_FOUND", "模块未安装")
        return row

    @staticmethod
    def _manifest(row: registry.InstalledModule) -> Manifest:
        return Manifest.model_validate(row.manifest())

    def _version_dir(self, module_id: str, version: str) -> Path:
        return self.modules_root / module_id / version

    # ------------------------------------------------------------------ 查询
    def list_modules(self) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = registry.list_installed(session)
            ever_enabled = audit.enabled_module_ids(session)
            result: list[dict[str, Any]] = []
            for row in rows:
                granted = registry.granted_scopes(session, row.id)
                result.append(
                    self._describe(row, granted, ever_enabled=row.id in ever_enabled)
                )
            return result

    def get_module(self, module_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._require_row(session, module_id)
            return self._describe(
                row,
                registry.granted_scopes(session, module_id),
                ever_enabled=audit.was_enabled(session, module_id),
            )

    def _describe(
        self,
        row: registry.InstalledModule,
        granted: list[str],
        *,
        ever_enabled: bool,
    ) -> dict[str, Any]:
        manifest = self._manifest(row)
        host = self._hosts.get(row.id)
        if not row.enabled:
            state = "disabled" if ever_enabled else "installed"
        elif host is not None and host.alive:
            state = "running"
        elif host is not None:
            state = "crashed"
        elif row.id in self._states:
            state = self._states[row.id]
        else:
            state = "enabled"
        return {
            "id": row.id,
            "name": manifest.name,
            "description": manifest.description,
            "version": row.version,
            "type": manifest.type.value,
            "enabled": row.enabled,
            "running": bool(host is not None and host.alive),
            "state": state,
            "requestedPermissions": list(manifest.permissions),
            "grantedPermissions": granted,
            "previousVersion": row.previous_version,
            "installedAt": registry.to_iso(row.installed_at),
            "updatedAt": registry.to_iso(row.updated_at),
        }

    def list_permissions(self, module_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._require_row(session, module_id)
            manifest = self._manifest(row)
            granted = registry.granted_scopes(session, module_id)
            return {
                "moduleId": module_id,
                "requested": list(manifest.permissions),
                "granted": granted,
                "available": sorted(set(manifest.permissions) - set(granted)),
            }

    def audit_events(
        self,
        *,
        module_id: str | None = None,
        action: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            events = audit.list_events(
                session,
                module_id=module_id,
                action=action,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
            )
            return [audit.event_to_dict(event) for event in events]

    # ------------------------------------------------------------------ 安装
    def install(self, package_path: str | Path, *, enable: bool = False) -> dict[str, Any]:
        path = Path(package_path)
        if path.suffix.lower() != ".ehmod" or not path.is_file():
            raise ModuleError("INVALID_INPUT", "需要本地 .ehmod 文件")
        staging = self.modules_root / ".staging" / f"{uuid.uuid4().hex}"
        try:
            with zipfile.ZipFile(path) as zf:
                report = package.extract_package(zf, staging)
            manifest = load_manifest_file(staging / "module.json")
            check_compatibility(manifest, core_version=self.core_version)
            package.verify_layout(staging, manifest)
            warnings = package.verify_checksums(staging)

            with self._lock_for(manifest.id):
                return self._commit_install(
                    staging, manifest, enable=enable, warnings=warnings, package_bytes=report.bytes
                )
        except zipfile.BadZipFile as exc:
            raise ModuleError("INVALID_PACKAGE", "不是合法的 ZIP 包") from exc
        except OSError as exc:
            raise ModuleError("INVALID_PACKAGE", "模块包安装失败") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _commit_install(
        self,
        staging: Path,
        manifest: Manifest,
        *,
        enable: bool,
        warnings: list[str],
        package_bytes: int,
    ) -> dict[str, Any]:
        target = self._version_dir(manifest.id, manifest.version)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as session:
            existing = registry.get_module(session, manifest.id)
            if existing is not None and existing.version == manifest.version:
                raise ModuleError(
                    "MODULE_ALREADY_INSTALLED",
                    "该模块版本已安装",
                    {"moduleId": manifest.id, "version": manifest.version},
                )
            if existing is None and target.exists():
                # 目录存在但注册表没有记录：视为上次失败遗留，允许覆盖。
                shutil.rmtree(target, ignore_errors=True)

            previous_version = existing.version if existing is not None else None
            currently_enabled = bool(existing.enabled) if existing is not None else False
            self._stop_host(manifest.id)

            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            try:
                staging.replace(target)

                enabled_after = enable or currently_enabled
                registry.upsert_installed(
                    session,
                    manifest,
                    enabled=enabled_after,
                    previous_version=previous_version,
                )

                if existing is None:
                    initial = [scope for scope in manifest.permissions if scope not in DEFAULT_DENIED_SCOPES]
                    for scope in initial:
                        registry.grant_scope(session, manifest.id, scope)
                    granted = set(initial)
                    added: list[str] = []
                    removed: list[str] = []
                    action = "module.install"
                else:
                    previously_granted = set(registry.granted_scopes(session, manifest.id))
                    keep = previously_granted & set(manifest.permissions)
                    registry.replace_granted(session, manifest.id, keep)
                    granted = keep
                    added, removed = diff_scopes(previously_granted, set(manifest.permissions))
                    action = "module.update"

                audit.append(
                    session,
                    action,
                    module_id=manifest.id,
                    detail={
                        "version": manifest.version,
                        "previousVersion": previous_version,
                        "files": len([p for p in target.rglob("*") if p.is_file()]),
                        "bytes": package_bytes,
                        "enabled": enabled_after,
                        "grantedPermissions": sorted(granted),
                        "addedPermissions": added,
                        "removedPermissions": removed,
                    },
                )
                session.flush()
                summary = self._describe(
                    self._require_row(session, manifest.id),
                    sorted(granted),
                    ever_enabled=audit.was_enabled(session, manifest.id),
                )
                summary["warnings"] = warnings
                summary["addedPermissions"] = added
            except Exception:
                # 文件已就位但注册失败时回滚目录，避免留下未注册的半成品。
                shutil.rmtree(target, ignore_errors=True)
                raise

        self._states.pop(manifest.id, None)
        self._crash_counts.pop(manifest.id, None)
        return summary

    def rollback(self, module_id: str, version: str | None = None) -> dict[str, Any]:
        with self._lock_for(module_id), self._session() as session:
            row = self._require_row(session, module_id)
            target_version = version or row.previous_version
            if not target_version:
                raise ModuleError("INVALID_INPUT", "没有可回滚的历史版本")
            if target_version == row.version:
                raise ModuleError("INVALID_INPUT", "目标版本与当前版本相同")
            directory = self._version_dir(module_id, target_version)
            if not directory.is_dir():
                raise ModuleError("MODULE_NOT_FOUND", "历史版本目录不存在",
                                  {"version": target_version})
            manifest = load_manifest_file(directory / "module.json")
            if manifest.version != target_version:
                raise ModuleError(
                    "INVALID_PACKAGE", "历史版本目录与 manifest 版本不一致", {"version": target_version}
                )
            check_compatibility(manifest, core_version=self.core_version)
            package.verify_layout(directory, manifest)
            package.verify_checksums(directory)

            self._stop_host(module_id)
            registry.set_version(session, row, target_version, manifest)
            previously_granted = set(registry.granted_scopes(session, module_id))
            keep = previously_granted & set(manifest.permissions)
            registry.replace_granted(session, module_id, keep)
            audit.append(
                session,
                "module.rollback",
                module_id=module_id,
                detail={
                    "version": target_version,
                    "previousVersion": row.previous_version,
                    "grantedPermissions": sorted(keep),
                },
            )
            summary = self._describe(
                row, sorted(keep), ever_enabled=audit.was_enabled(session, module_id)
            )
            session.commit()
        self._crash_counts.pop(module_id, None)
        return summary

    # ------------------------------------------------------------------ 生命周期
    def enable(self, module_id: str) -> dict[str, Any]:
        with self._lock_for(module_id), self._session() as session:
            row = self._require_row(session, module_id)
            if not row.enabled:
                registry.set_enabled(session, row, True)
                audit.append(session, "module.enable", module_id=module_id)
            summary = self._describe(
                row, registry.granted_scopes(session, module_id), ever_enabled=True
            )
            session.commit()
        self._states.pop(module_id, None)
        self._crash_counts.pop(module_id, None)
        return summary

    def disable(self, module_id: str) -> dict[str, Any]:
        with self._lock_for(module_id):
            self._stop_host(module_id)
            with self._session() as session:
                row = self._require_row(session, module_id)
                if row.enabled:
                    registry.set_enabled(session, row, False)
                    audit.append(session, "module.disable", module_id=module_id)
                summary = self._describe(
                    row,
                    registry.granted_scopes(session, module_id),
                    ever_enabled=audit.was_enabled(session, module_id),
                )
                session.commit()
        self._states.pop(module_id, None)
        return summary

    def start(self, module_id: str) -> dict[str, Any]:
        with self._lock_for(module_id):
            with self._session() as session:
                row = self._require_row(session, module_id)
                if not row.enabled:
                    raise ModuleError("MODULE_DISABLED", "模块未启用")
                manifest = self._manifest(row)
                granted = registry.granted_scopes(session, module_id)
            self._crash_counts.pop(module_id, None)
            started = self._ensure_host(module_id, manifest, granted)
            if started:
                with self._session() as session:
                    audit.append(session, "module.start", module_id=module_id)
            with self._session() as session:
                row = self._require_row(session, module_id)
                return self._describe(
                    row, registry.granted_scopes(session, module_id), ever_enabled=True
                )

    def stop(self, module_id: str) -> dict[str, Any]:
        with self._lock_for(module_id), self._session() as session:
            row = self._require_row(session, module_id)
            self._stop_host(module_id)
            self._states[module_id] = "stopped"
            audit.append(session, "module.stop", module_id=module_id)
            summary = self._describe(
                row,
                registry.granted_scopes(session, module_id),
                ever_enabled=audit.was_enabled(session, module_id),
            )
            session.commit()
            return summary

    def uninstall(self, module_id: str, *, keep_data: bool = False) -> dict[str, Any]:
        with self._lock_for(module_id):
            with self._session() as session:
                self._require_row(session, module_id)
            self._stop_host(module_id)
            module_root = self.modules_root / module_id
            preserved: Path | None = None
            data_dir = module_root / "data"
            backup = self.modules_root / ".keep" / f"{module_id}-{uuid.uuid4().hex}"
            if keep_data and data_dir.is_dir():
                try:
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    data_dir.replace(backup)
                    preserved = backup
                except OSError as exc:
                    raise ModuleError("MODULE_ERROR", "卸载时无法保留模块数据") from exc
            if module_root.exists():
                try:
                    shutil.rmtree(module_root)
                except OSError as exc:
                    if preserved is not None and preserved.exists():
                        module_root.mkdir(parents=True, exist_ok=True)
                        preserved.replace(module_root / "data")
                    raise ModuleError("MODULE_ERROR", "卸载时无法清理模块目录") from exc

            with self._session() as session:
                audit.append(
                    session,
                    "module.uninstall",
                    module_id=module_id,
                    detail={"keepData": keep_data},
                )
                registry.delete_module(session, module_id)

            if keep_data:
                module_root.mkdir(parents=True, exist_ok=True)
                if preserved is not None and preserved.exists():
                    preserved.replace(module_root / "data")
                shutil.rmtree(backup.parent, ignore_errors=True)

        self._states.pop(module_id, None)
        self._crash_counts.pop(module_id, None)
        return {"moduleId": module_id, "uninstalled": True, "keptData": keep_data}

    # ------------------------------------------------------------------ 权限
    def grant_permission(self, module_id: str, scope: str) -> dict[str, Any]:
        validate_scope(scope)
        with self._lock_for(module_id), self._session() as session:
            row = self._require_row(session, module_id)
            manifest = self._manifest(row)
            if scope not in manifest.permissions:
                raise ModuleError("INVALID_INPUT", "模块安装时未请求该权限",
                                  {"scope": scope})
            if registry.grant_scope(session, module_id, scope):
                audit.append(session, "permission.grant", module_id=module_id, scope=scope)
            granted = registry.granted_scopes(session, module_id)
            session.commit()
            return {
                "moduleId": module_id,
                "requested": list(manifest.permissions),
                "granted": granted,
                "available": sorted(set(manifest.permissions) - set(granted)),
            }

    def revoke_permission(self, module_id: str, scope: str) -> dict[str, Any]:
        validate_scope(scope)
        with self._lock_for(module_id):
            host_running = self._hosts.get(module_id, None) is not None
            with self._session() as session:
                row = self._require_row(session, module_id)
                manifest = self._manifest(row)
                if registry.revoke_scope(session, module_id, scope):
                    audit.append(session, "permission.revoke", module_id=module_id, scope=scope)
                granted = registry.granted_scopes(session, module_id)
                session.commit()
            if host_running:
                # 已启动的 worker 里权限是启动时注入的；撤销后必须重启才能生效。
                self._stop_host(module_id)
                self._states[module_id] = "stopped"
            return {
                "moduleId": module_id,
                "requested": list(manifest.permissions),
                "granted": granted,
                "available": sorted(set(manifest.permissions) - set(granted)),
            }

    # ------------------------------------------------------------------ RPC
    def call(self, module_id: str, method: str, params: dict[str, Any] | None = None) -> Any:
        if not method or len(method) > 128:
            raise ModuleError("INVALID_INPUT", "方法名无效")
        params = params or {}
        with self._lock_for(module_id):
            with self._session() as session:
                row = self._require_row(session, module_id)
                if not row.enabled:
                    raise ModuleError("MODULE_DISABLED", "模块未启用")
                manifest = self._manifest(row)
                granted = registry.granted_scopes(session, module_id)

            started_at = time.perf_counter()
            ok = False
            error_code: str | None = None
            try:
                host_missing = self._hosts.get(module_id) is None
                if (
                    host_missing
                    and self._states.get(module_id) == "crashed"
                    and self._crash_counts.get(module_id, 0) > self.max_restarts
                ):
                    raise ModuleError("MODULE_CRASH", "模块连续崩溃，需要手动 start")
                self._ensure_host(module_id, manifest, granted)
                result = self._request_with_recovery(module_id, manifest, granted, method, params)
                ok = True
                self._crash_counts.pop(module_id, None)
                return result
            except ModuleError as exc:
                error_code = exc.code
                raise
            finally:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                with self._session() as session:
                    audit.append(
                        session,
                        "rpc.call",
                        module_id=module_id,
                        detail={
                            "method": method,
                            "durationMs": duration_ms,
                            "ok": ok,
                            "errorCode": error_code,
                        },
                    )

    def _request_with_recovery(
        self,
        module_id: str,
        manifest: Manifest,
        granted: list[str],
        method: str,
        params: dict[str, Any],
    ) -> Any:
        host = self._hosts.get(module_id)
        if host is None or not host.alive:
            raise ModuleError("MODULE_CRASH", "模块进程未运行")
        try:
            return host.request(method, params, timeout=self.call_timeout_s)
        except ModuleError as exc:
            if exc.code == "MODULE_TIMEOUT":
                host.stop()
                self._hosts.pop(module_id, None)
                self._states[module_id] = "stopped"
                raise
            if exc.code != "MODULE_CRASH":
                raise
            host.stop()
            self._hosts.pop(module_id, None)
            restarts = self._crash_counts.get(module_id, 0) + 1
            self._crash_counts[module_id] = restarts
            self._states[module_id] = "crashed"
            with self._session() as session:
                audit.append(
                    session,
                    "module.crash",
                    module_id=module_id,
                    detail={"restarts": restarts - 1, "method": method},
                )
            if restarts <= self.max_restarts:
                try:
                    self._ensure_host(module_id, manifest, granted)
                    with self._session() as session:
                        audit.append(session, "module.restart", module_id=module_id,
                                     detail={"method": method})
                except ModuleError:
                    pass
            raise

    def _ensure_host(self, module_id: str, manifest: Manifest, granted: list[str]) -> bool:
        host = self._hosts.get(module_id)
        if host is not None and host.alive:
            return False
        if host is not None:
            # 空闲时进程自行退出：没有请求上下文，也要留下崩溃审计并计入重启预算。
            crashed = not host.alive
            if crashed:
                crashes = self._crash_counts.get(module_id, 0) + 1
                self._crash_counts[module_id] = crashes
                with self._session() as session:
                    audit.append(
                        session,
                        "module.crash",
                        module_id=module_id,
                        detail={"reason": "idle-exit", "crashes": crashes},
                    )
                self._states[module_id] = "crashed"
            host.stop()
            self._hosts.pop(module_id, None)
            if crashed and self._crash_counts.get(module_id, 0) > self.max_restarts:
                raise ModuleError("MODULE_CRASH", "模块连续崩溃，需要手动 start")
        module_dir = self._version_dir(module_id, manifest.version)
        if not (module_dir / manifest.entry_path).is_file():
            raise ModuleError("MODULE_CRASH", "模块入口文件缺失")
        host = ModuleHost(
            module_id=module_id,
            module_dir=module_dir,
            entry_python=manifest.entry_path,
            log_path=self.logs_root / f"{module_id}.log",
            permissions=granted,
            locale=self.locale,
            startup_timeout_s=manifest.startup_timeout_s,
            call_timeout_s=self.call_timeout_s,
            core_call_handler=lambda method, params: self._handle_core_call(module_id, method, params),
        )
        host.start()
        self._hosts[module_id] = host
        self._states[module_id] = "running"
        return True

    def _stop_host(self, module_id: str) -> None:
        host = self._hosts.pop(module_id, None)
        if host is not None:
            host.stop()
            if module_id in self._states:
                self._states[module_id] = "stopped"

    # ------------------------------------------------------------------ 核心回调
    def _handle_core_call(self, module_id: str, method: str, params: dict[str, Any]) -> Any:
        with self._session() as session:
            row = registry.get_module(session, module_id)
            if row is None:
                raise ModuleError("MODULE_NOT_FOUND", "模块未安装")
            granted = set(registry.granted_scopes(session, module_id))
            known, scope = required_scope(method)
            try:
                check_core_call(granted, method)
            except ModuleError as exc:
                audit.append(
                    session,
                    "core.call",
                    module_id=module_id,
                    scope=scope,
                    detail={"method": method, "ok": False, "errorCode": exc.code},
                )
                # 越权也要留痕：显式提交后再抛给 worker。
                session.commit()
                raise

            if method == "log.write":
                level = str(params.get("level", "info"))[:16]
                message = str(params.get("message", ""))[:500]
                self._append_module_log(module_id, f"[{level}] {message}")
                result: Any = {"ok": True}
            elif method == "events.emit":
                result = {"ok": True}
            elif method == "audit.write":
                audit.append(
                    session,
                    "module.event",
                    module_id=module_id,
                    detail={"event": str(params.get("event", ""))[:64]},
                )
                result = {"ok": True}
            else:
                audit.append(
                    session,
                    "core.call",
                    module_id=module_id,
                    scope=scope,
                    detail={"method": method, "ok": False, "errorCode": "NOT_IMPLEMENTED"},
                )
                session.commit()
                raise ModuleError("NOT_IMPLEMENTED", "该核心方法将在后续批次接线",
                                  {"method": method[:64]})
            audit.append(
                session,
                "core.call",
                module_id=module_id,
                scope=scope,
                detail={"method": method, "ok": True, "known": known},
            )
            return result

    def _append_module_log(self, module_id: str, message: str) -> None:
        path = self.logs_root / f"{module_id}.log"
        try:
            with path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(f"[core] {message}\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ 关闭
    def shutdown(self) -> None:
        with self._op_lock:
            for module_id in list(self._hosts):
                self._stop_host(module_id)
            self._states.clear()


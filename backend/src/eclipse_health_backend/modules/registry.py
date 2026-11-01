"""模块注册表：已安装模块与权限。表挂到核心 Base 的 metadata 上（见 db_compat）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Text, select
from sqlalchemy.orm import Session
from sqlmodel import Field

from ..db.base import Base
from .manifest import Manifest


def utcnow() -> datetime:
    """SQLite 不保留时区，统一存 naive UTC。"""
    return datetime.now(UTC).replace(tzinfo=None)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class InstalledModule(Base, table=True):
    __tablename__ = "installed_modules"

    id: str = Field(primary_key=True, max_length=128)
    version: str = Field(max_length=64)
    enabled: bool = Field(default=False)
    manifest_json: str = Field(sa_column=Column(Text, nullable=False))
    installed_at: datetime = Field(sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime, nullable=False))
    # update 时保留上一版本，供最简回滚使用。
    previous_version: str | None = Field(default=None, max_length=64)

    def manifest(self) -> dict[str, Any]:
        return json.loads(self.manifest_json)


class ModulePermission(Base, table=True):
    __tablename__ = "module_permissions"

    module_id: str = Field(primary_key=True, max_length=128)
    scope: str = Field(primary_key=True, max_length=64)
    granted_at: datetime = Field(sa_column=Column(DateTime, nullable=False))


def get_module(session: Session, module_id: str) -> InstalledModule | None:
    return session.get(InstalledModule, module_id)


def list_installed(session: Session) -> list[InstalledModule]:
    return list(session.scalars(select(InstalledModule).order_by(InstalledModule.id)))


def upsert_installed(
    session: Session,
    manifest: Manifest,
    *,
    enabled: bool,
    previous_version: str | None = None,
    now: datetime | None = None,
) -> InstalledModule:
    timestamp = now or utcnow()
    row = session.get(InstalledModule, manifest.id)
    payload = json.dumps(manifest.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
    if row is None:
        row = InstalledModule(
            id=manifest.id,
            version=manifest.version,
            enabled=enabled,
            manifest_json=payload,
            installed_at=timestamp,
            updated_at=timestamp,
            previous_version=previous_version,
        )
        session.add(row)
    else:
        if previous_version is not None:
            row.previous_version = previous_version
        row.version = manifest.version
        row.enabled = enabled
        row.manifest_json = payload
        row.updated_at = timestamp
    session.flush()
    return row


def set_enabled(session: Session, row: InstalledModule, enabled: bool, now: datetime | None = None) -> None:
    row.enabled = enabled
    row.updated_at = now or utcnow()
    session.add(row)
    session.flush()


def set_version(
    session: Session,
    row: InstalledModule,
    version: str,
    manifest: Manifest,
    now: datetime | None = None,
) -> None:
    row.previous_version = row.version if row.version != version else row.previous_version
    row.version = version
    row.manifest_json = json.dumps(manifest.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
    row.updated_at = now or utcnow()
    session.add(row)
    session.flush()


def delete_module(session: Session, module_id: str) -> None:
    row = session.get(InstalledModule, module_id)
    if row is not None:
        session.delete(row)
    for permission in list(session.scalars(select(ModulePermission).where(ModulePermission.module_id == module_id))):
        session.delete(permission)
    session.flush()


def granted_scopes(session: Session, module_id: str) -> list[str]:
    rows = session.scalars(
        select(ModulePermission.scope)
        .where(ModulePermission.module_id == module_id)
        .order_by(ModulePermission.scope)
    )
    return list(rows)


def permission_rows(session: Session, module_id: str) -> list[ModulePermission]:
    return list(
        session.scalars(
            select(ModulePermission)
            .where(ModulePermission.module_id == module_id)
            .order_by(ModulePermission.scope)
        )
    )


def grant_scope(session: Session, module_id: str, scope: str, now: datetime | None = None) -> bool:
    if session.get(ModulePermission, (module_id, scope)) is not None:
        return False
    session.add(ModulePermission(module_id=module_id, scope=scope, granted_at=now or utcnow()))
    session.flush()
    return True


def revoke_scope(session: Session, module_id: str, scope: str) -> bool:
    row = session.get(ModulePermission, (module_id, scope))
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def replace_granted(session: Session, module_id: str, scopes: set[str], now: datetime | None = None) -> None:
    existing = {row.scope for row in permission_rows(session, module_id)}
    for scope in existing - scopes:
        revoke_scope(session, module_id, scope)
    for scope in scopes - existing:
        grant_scope(session, module_id, scope, now=now)
    session.flush()


def revoke_all(session: Session, module_id: str) -> None:
    replace_granted(session, module_id, set())

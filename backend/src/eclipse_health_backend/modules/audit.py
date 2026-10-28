"""只追加审计日志（契约 §11）。

绝不写入波形、notes、payload 原文或任何健康数据内容；只记录 ID、范围与大小。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, Text, event, select
from sqlalchemy.orm import Session
from sqlmodel import Field

from ..db.base import Base
from .ids import audit_event_id
from .registry import to_iso, to_naive_utc, utcnow

# 契约 §11 预留的审计动作；数据层在后续批次接线时直接复用这些名字。
RESERVED_ACTIONS = frozenset({"data.read", "data.write"})

_FORBIDDEN_KEYS = {
    "payload",
    "payload_json",
    "signal",
    "signals",
    "beats",
    "notes",
    "content",
    "waveform",
    "params",
    "data",
    "record",
    "records",
    "text",
    "body",
}
_MAX_STRING = 300


class AuditEvent(Base, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_module_action", "module_id", "action"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id: str = Field(primary_key=True, max_length=64)
    module_id: str | None = Field(default=None, max_length=128)
    action: str = Field(max_length=64)
    scope: str | None = Field(default=None, max_length=64)
    detail_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime, nullable=False))


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _append_only(*_args: object) -> None:
    raise RuntimeError("audit_log is append-only")


def sanitize_detail(value: Any, depth: int = 0) -> Any:
    """保留可观测元数据（方法名、耗时、大小），剔除任何内容字段。"""
    if depth > 3:
        return None
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_KEYS:
                continue
            sanitized = sanitize_detail(item, depth + 1)
            if sanitized is not None:
                cleaned[key[:_MAX_STRING]] = sanitized
        return cleaned
    if isinstance(value, list | tuple):
        items = [sanitize_detail(item, depth + 1) for item in value[:32]]
        return [item for item in items if item is not None]
    return None


def append(
    session: Session,
    action: str,
    *,
    module_id: str | None = None,
    scope: str | None = None,
    detail: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=audit_event_id(),
        module_id=module_id,
        action=action[:64],
        scope=scope[:64] if scope else None,
        detail_json=json.dumps(sanitize_detail(detail), ensure_ascii=False) if detail else None,
        created_at=now or utcnow(),
    )
    session.add(event)
    session.flush()
    return event


def enabled_module_ids(session: Session) -> set[str]:
    """曾经启用过的模块；用于区分「刚安装未启用」与「被禁用」。"""
    rows = session.scalars(
        select(AuditEvent.module_id)
        .where(AuditEvent.action == "module.enable", AuditEvent.module_id.is_not(None))
        .distinct()
    )
    return {module_id for module_id in rows if module_id}


def was_enabled(session: Session, module_id: str) -> bool:
    return (
        session.scalar(
            select(AuditEvent.id)
            .where(AuditEvent.module_id == module_id, AuditEvent.action == "module.enable")
            .limit(1)
        )
        is not None
    )


def list_events(
    session: Session,
    *,
    module_id: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    statement = select(AuditEvent)
    if module_id:
        statement = statement.where(AuditEvent.module_id == module_id)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if since:
        statement = statement.where(AuditEvent.created_at >= to_naive_utc(since))
    if until:
        statement = statement.where(AuditEvent.created_at <= to_naive_utc(until))
    statement = statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    statement = statement.offset(max(0, offset)).limit(max(1, min(limit, 1000)))
    return list(session.scalars(statement))


def event_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "moduleId": event.module_id,
        "action": event.action,
        "scope": event.scope,
        "detail": json.loads(event.detail_json) if event.detail_json else None,
        "createdAt": to_iso(event.created_at),
    }

"""LLM 会话持久化：``assistant_sessions`` / ``assistant_messages`` / ``assistant_tool_calls``。

只存对话、透明面板所需的最小元数据与工具调用摘要；**不存工具完整返回值**，
避免把健康数据在会话表里再复制一份（Schema §15 隐私原则）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, literal_column
from sqlmodel import Field, Session, select

from ..domain.common import to_storage_dt, utc_now
from ..domain.ids import uuid7
from .base import Base

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

STATUS_STREAMING = "streaming"
STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


def new_session_id() -> str:
    return f"lsn_{uuid7()}"


def new_message_id() -> str:
    return f"lmsg_{uuid7()}"


def new_tool_call_id() -> str:
    return f"ltc_{uuid7()}"


class AssistantSessionTable(Base, table=True):
    __tablename__ = "assistant_sessions"

    id: str = Field(primary_key=True)
    member_id: str = Field(foreign_key="members.id", index=True)
    title: str = Field(default="新会话")
    provider_id: str | None = Field(default=None, index=True)
    style: str = Field(default="brief")
    record_id: str | None = Field(default=None, index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime
    updated_at: datetime


class AssistantMessageTable(Base, table=True):
    __tablename__ = "assistant_messages"

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="assistant_sessions.id", index=True)
    role: str = Field(index=True)
    content: str = Field(default="")
    status: str = Field(default=STATUS_COMPLETED, index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime


class AssistantToolCallTable(Base, table=True):
    __tablename__ = "assistant_tool_calls"

    id: str = Field(primary_key=True)
    message_id: str = Field(foreign_key="assistant_messages.id", index=True)
    session_id: str = Field(foreign_key="assistant_sessions.id", index=True)
    name: str = Field(index=True)
    args: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    result_summary: str = Field(default="")
    ok: bool = Field(default=True)
    duration_ms: int = Field(default=0)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


def session_to_dict(row: AssistantSessionTable, *, message_count: int = 0) -> dict[str, Any]:
    data = row.data or {}
    return {
        "id": row.id,
        "title": row.title,
        "providerId": row.provider_id,
        "style": row.style,
        "recordId": row.record_id,
        "messageCount": message_count,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
        "hasNotes": bool(data.get("hasNotes", False)),
    }


def create_session(
    session: Session,
    *,
    member_id: str,
    title: str = "新会话",
    provider_id: str | None = None,
    style: str = "brief",
    record_id: str | None = None,
    session_id: str | None = None,
) -> AssistantSessionTable:
    now = utc_now()
    row = AssistantSessionTable(
        id=session_id or new_session_id(),
        member_id=member_id,
        title=(title or "新会话").strip()[:120] or "新会话",
        provider_id=provider_id,
        style=style,
        record_id=record_id,
        data={},
        created_at=to_storage_dt(now),
        updated_at=to_storage_dt(now),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_session_row(session: Session, session_id: str) -> AssistantSessionTable | None:
    return session.get(AssistantSessionTable, session_id)


def list_session_rows(
    session: Session, member_id: str, *, limit: int = 50, offset: int = 0
) -> list[AssistantSessionTable]:
    statement = (
        select(AssistantSessionTable)
        .where(AssistantSessionTable.member_id == member_id)
        .order_by(AssistantSessionTable.updated_at.desc(), AssistantSessionTable.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(statement))


def count_messages(session: Session, session_id: str) -> int:
    from sqlalchemy import func

    statement = select(func.count()).select_from(AssistantMessageTable).where(
        AssistantMessageTable.session_id == session_id
    )
    return int(session.exec(statement).one() or 0)


def touch_session(
    session: Session,
    row: AssistantSessionTable,
    *,
    title: str | None = None,
    provider_id: str | None = None,
    style: str | None = None,
    record_id: str | None = None,
    has_notes: bool | None = None,
    commit: bool = True,
) -> AssistantSessionTable:
    if title is not None and title.strip():
        row.title = title.strip()[:120]
    if provider_id is not None:
        row.provider_id = provider_id
    if style is not None:
        row.style = style
    if record_id is not None:
        row.record_id = record_id
    if has_notes is not None:
        data = dict(row.data or {})
        data["hasNotes"] = bool(has_notes)
        row.data = data
    row.updated_at = to_storage_dt(utc_now())
    session.add(row)
    if commit:
        session.commit()
    return row


def delete_session(session: Session, session_id: str) -> bool:
    row = get_session_row(session, session_id)
    if row is None:
        return False
    for call in session.exec(
        select(AssistantToolCallTable).where(AssistantToolCallTable.session_id == session_id)
    ):
        session.delete(call)
    for message in session.exec(
        select(AssistantMessageTable).where(AssistantMessageTable.session_id == session_id)
    ):
        session.delete(message)
    session.delete(row)
    session.commit()
    return True


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #


def message_to_dict(
    row: AssistantMessageTable, tool_calls: list[AssistantToolCallTable]
) -> dict[str, Any]:
    data = row.data or {}
    return {
        "id": row.id,
        "sessionId": row.session_id,
        "role": row.role,
        "content": row.content,
        "status": row.status,
        "providerId": data.get("providerId"),
        "style": data.get("style"),
        "citations": data.get("citations") or [],
        "error": data.get("error"),
        "toolCalls": [tool_call_to_dict(call) for call in tool_calls],
        "createdAt": row.created_at.isoformat(),
    }


def tool_call_to_dict(row: AssistantToolCallTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "messageId": row.message_id,
        "name": row.name,
        "args": row.args or {},
        "resultSummary": row.result_summary,
        "ok": row.ok,
        "durationMs": row.duration_ms,
        "createdAt": row.created_at.isoformat(),
    }


def add_message(
    session: Session,
    *,
    session_id: str,
    role: str,
    content: str = "",
    status: str = STATUS_COMPLETED,
    data: dict[str, Any] | None = None,
    message_id: str | None = None,
    commit: bool = True,
) -> AssistantMessageTable:
    row = AssistantMessageTable(
        id=message_id or new_message_id(),
        session_id=session_id,
        role=role,
        content=content,
        status=status,
        data=data or {},
        created_at=to_storage_dt(utc_now()),
    )
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
    return row


def update_message(
    session: Session,
    row: AssistantMessageTable,
    *,
    content: str | None = None,
    status: str | None = None,
    data: dict[str, Any] | None = None,
    commit: bool = True,
) -> AssistantMessageTable:
    if content is not None:
        row.content = content
    if status is not None:
        row.status = status
    if data is not None:
        row.data = data
    session.add(row)
    if commit:
        session.commit()
    return row


def get_message_row(session: Session, message_id: str) -> AssistantMessageTable | None:
    return session.get(AssistantMessageTable, message_id)


def list_message_rows(
    session: Session, session_id: str, *, limit: int = 200, offset: int = 0
) -> list[AssistantMessageTable]:
    # user/assistant 可能落在同一微秒且 UUIDv7 同毫秒，用 rowid 保证严格的插入顺序。
    statement = (
        select(AssistantMessageTable)
        .where(AssistantMessageTable.session_id == session_id)
        .order_by(AssistantMessageTable.created_at, literal_column("assistant_messages.rowid"))
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(statement))


def list_tool_calls(session: Session, message_id: str) -> list[AssistantToolCallTable]:
    statement = (
        select(AssistantToolCallTable)
        .where(AssistantToolCallTable.message_id == message_id)
        .order_by(
            AssistantToolCallTable.created_at,
            literal_column("assistant_tool_calls.rowid"),
        )
    )
    return list(session.exec(statement))


def add_tool_call(
    session: Session,
    *,
    message_id: str,
    session_id: str,
    name: str,
    args: dict[str, Any],
    result_summary: str,
    ok: bool,
    duration_ms: int,
    data: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
    commit: bool = True,
) -> AssistantToolCallTable:
    row = AssistantToolCallTable(
        id=tool_call_id or new_tool_call_id(),
        message_id=message_id,
        session_id=session_id,
        name=name,
        args=args,
        result_summary=result_summary[:500],
        ok=ok,
        duration_ms=max(0, int(duration_ms)),
        data=data or {},
        created_at=to_storage_dt(utc_now()),
    )
    session.add(row)
    if commit:
        session.commit()
    return row


def transparency_of(row: AssistantMessageTable) -> dict[str, Any] | None:
    data = row.data or {}
    value = data.get("transparency")
    return value if isinstance(value, dict) else None


def history_for_prompt(
    session: Session, session_id: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """取最近 N 轮 user/assistant 文本，作为模型上下文。"""
    rows = list_message_rows(session, session_id, limit=10_000)
    trimmed = [row for row in rows if row.role in {ROLE_USER, ROLE_ASSISTANT} and row.content]
    return [{"role": row.role, "content": row.content} for row in trimmed[-limit:]]


__all__ = [
    "ROLE_ASSISTANT",
    "ROLE_USER",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_ERROR",
    "STATUS_STREAMING",
    "AssistantMessageTable",
    "AssistantSessionTable",
    "AssistantToolCallTable",
    "add_message",
    "add_tool_call",
    "count_messages",
    "create_session",
    "delete_session",
    "get_message_row",
    "get_session_row",
    "history_for_prompt",
    "list_message_rows",
    "list_session_rows",
    "list_tool_calls",
    "message_to_dict",
    "new_message_id",
    "new_session_id",
    "new_tool_call_id",
    "session_to_dict",
    "tool_call_to_dict",
    "touch_session",
    "transparency_of",
    "update_message",
]

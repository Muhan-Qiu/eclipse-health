"""领域模型 <-> 表模型的转换与最小持久化助手。

API 层的分页/过滤查询留在 ``api/``，这里只负责单对象读写，保持 B1-02 也能复用。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from ..domain.common import to_storage_dt, utc_now
from ..domain.ids import new_id
from ..domain.models import (
    HealthRecord,
    Member,
    Signal,
    SignalStorage,
)
from .models import MemberTable, RecordTable, SignalTable


def _member_row_from_model(member: Member) -> MemberTable:
    return MemberTable(
        id=member.id,
        display_name=member.displayName,
        data=member.model_dump(by_alias=True, mode="json"),
        created_at=to_storage_dt(member.createdAt),
        updated_at=to_storage_dt(member.updatedAt),
    )


def member_from_row(row: MemberTable) -> Member:
    return Member.model_validate(row.data)


def add_member(session: Session, member: Member) -> Member:
    session.add(_member_row_from_model(member))
    session.commit()
    return member


def get_member_row(session: Session, member_id: str) -> MemberTable | None:
    return session.get(MemberTable, member_id)


def list_member_rows(session: Session) -> list[MemberTable]:
    return list(session.exec(select(MemberTable).order_by(MemberTable.created_at)))


def update_member_row(session: Session, row: MemberTable, member: Member) -> Member:
    row.display_name = member.displayName
    row.data = member.model_dump(by_alias=True, mode="json")
    row.updated_at = to_storage_dt(member.updatedAt)
    session.add(row)
    session.commit()
    return member


def build_default_member() -> Member:
    now = utc_now()
    return Member(
        id=new_id("member"),
        displayName="本人",
        createdAt=now,
        updatedAt=now,
    )


def ensure_default_member(session: Session) -> Member:
    """首次启动自动建默认成员「本人」；已有成员则原样返回第一个。"""
    rows = list_member_rows(session)
    if rows:
        return member_from_row(rows[0])
    member = build_default_member()
    add_member(session, member)
    return member


def _record_row_from_model(record: HealthRecord) -> RecordTable:
    dumped: dict[str, Any] = record.model_dump(by_alias=True, mode="json")
    payload = dumped.pop("payload", {})
    return RecordTable(
        id=record.id,
        member_id=record.memberId,
        record_type=record.recordType,
        module_id=record.moduleId,
        captured_at=to_storage_dt(record.capturedAt),
        data=dumped,
        payload=payload,
        created_at=to_storage_dt(record.createdAt),
        updated_at=to_storage_dt(record.updatedAt),
        deleted_at=to_storage_dt(record.deletedAt) if record.deletedAt else None,
    )


def record_from_row(row: RecordTable) -> HealthRecord:
    data = dict(row.data)
    data["payload"] = row.payload or {}
    return HealthRecord.model_validate(data)


def add_record(session: Session, record: HealthRecord, *, commit: bool = True) -> HealthRecord:
    session.add(_record_row_from_model(record))
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def get_record_row(session: Session, record_id: str) -> RecordTable | None:
    return session.get(RecordTable, record_id)


def update_record_row(
    session: Session, row: RecordTable, record: HealthRecord, *, commit: bool = True
) -> HealthRecord:
    fresh = _record_row_from_model(record)
    row.member_id = fresh.member_id
    row.record_type = fresh.record_type
    row.module_id = fresh.module_id
    row.captured_at = fresh.captured_at
    row.data = fresh.data
    row.payload = fresh.payload
    row.updated_at = fresh.updated_at
    row.deleted_at = fresh.deleted_at
    session.add(row)
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def _signal_row_from_model(signal: Signal) -> SignalTable:
    return SignalTable(
        id=signal.id,
        record_id=signal.recordId,
        lead=signal.lead,
        fs=signal.fs,
        unit=signal.unit,
        n_samples=signal.n_samples,
        relative_path=signal.storage.relativePath,
        sha256=signal.storage.sha256,
        data=signal.model_dump(by_alias=True, mode="json"),
        created_at=to_storage_dt(signal.createdAt),
    )


def signal_from_row(row: SignalTable) -> Signal:
    return Signal.model_validate(row.data)


def add_signal(session: Session, signal: Signal, *, commit: bool = True) -> Signal:
    session.add(_signal_row_from_model(signal))
    if commit:
        session.commit()
    else:
        session.flush()
    return signal


def list_signal_rows(session: Session, record_id: str) -> list[SignalTable]:
    statement = (
        select(SignalTable)
        .where(SignalTable.record_id == record_id)
        .order_by(SignalTable.created_at, SignalTable.id)
    )
    return list(session.exec(statement))


def get_signal_row(session: Session, record_id: str, lead: str) -> SignalTable | None:
    statement = select(SignalTable).where(
        SignalTable.record_id == record_id, SignalTable.lead == lead
    )
    return session.exec(statement).first()


def make_signal(
    *,
    record_id: str,
    lead: str,
    fs: float,
    unit: str,
    n_samples: int,
    relative_path: str,
    sha256: str,
    created_at: Any = None,
    signal_id: str | None = None,
) -> Signal:
    from ..domain.common import utc_now

    return Signal(
        id=signal_id or new_id("signal"),
        recordId=record_id,
        lead=lead,
        fs=fs,
        unit=unit,
        shape=[n_samples],
        storage=SignalStorage(relativePath=relative_path, sha256=sha256),
        createdAt=created_at or utc_now(),
    )


__all__ = [
    "add_member",
    "add_record",
    "add_signal",
    "ensure_default_member",
    "get_member_row",
    "get_record_row",
    "get_signal_row",
    "list_member_rows",
    "list_signal_rows",
    "make_signal",
    "member_from_row",
    "record_from_row",
    "signal_from_row",
    "update_member_row",
    "update_record_row",
]

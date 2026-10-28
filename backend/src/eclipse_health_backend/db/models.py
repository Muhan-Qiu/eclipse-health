"""SQLite 表模型（Schema §11）。

约定：
- 查询用列（id/memberId/recordType/...）单独建列，完整对象放 JSON 列 ``data``；
- ``records.payload`` 按 Schema 要求单独成列；
- 时间列使用 SQLModel 的 UTCDateTime：入库前统一转 UTC，读出即带时区。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field

from .base import Base


class MemberTable(Base, table=True):
    __tablename__ = "members"

    id: str = Field(primary_key=True)
    display_name: str = Field(index=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime
    updated_at: datetime


class RecordTable(Base, table=True):
    __tablename__ = "records"

    id: str = Field(primary_key=True)
    member_id: str = Field(foreign_key="members.id", index=True)
    record_type: str = Field(index=True)
    module_id: str | None = Field(default=None, index=True)
    captured_at: datetime = Field(index=True)
    # 完整记录对象（不含 payload），payload 单独列。
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = Field(default=None, index=True)


class SignalTable(Base, table=True):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("record_id", "lead", name="uq_signals_record_lead"),)

    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="records.id", index=True)
    lead: str = Field(index=True)
    fs: float
    unit: str
    n_samples: int
    relative_path: str
    sha256: str
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime


class AnalysisTable(Base, table=True):
    __tablename__ = "analyses"

    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="records.id", index=True)
    module_id: str | None = Field(default=None, index=True)
    model_id: str | None = Field(default=None, index=True)
    status: str = Field(index=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime


class MeasurementTable(Base, table=True):
    __tablename__ = "measurements"

    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="records.id", index=True)
    analysis_id: str | None = Field(default=None, foreign_key="analyses.id", index=True)
    code: str = Field(index=True)
    value: float | None = Field(default=None)
    unit: str | None = Field(default=None)
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime


class AnnotationTable(Base, table=True):
    __tablename__ = "annotations"

    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="records.id", index=True)
    analysis_id: str | None = Field(default=None, foreign_key="analyses.id", index=True)
    type: str = Field(index=True)
    label: str | None = Field(default=None, index=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime


class ReportTable(Base, table=True):
    __tablename__ = "reports"

    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="records.id", index=True)
    analysis_id: str | None = Field(default=None, foreign_key="analyses.id", index=True)
    format: str = Field(index=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime


__all__ = [
    "AnalysisTable",
    "AnnotationTable",
    "MeasurementTable",
    "MemberTable",
    "RecordTable",
    "ReportTable",
    "SignalTable",
]

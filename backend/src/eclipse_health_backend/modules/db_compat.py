"""核心数据库接口适配（B1-01 所有）。

模块内核不拥有 Base/engine：直接复用 ``db/base.py`` 的 metadata 与 engine，
表在 registry.py / audit.py 中声明后自动注册进同一份 metadata。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.schema import MetaData

from ..db.base import Base
from ..db.base import engine as core_engine
from ..settings import get_settings


def resolve_data_dir() -> Path:
    return get_settings().data_dir.resolve()


def get_metadata() -> MetaData:
    return Base.metadata


@dataclass(slots=True)
class DatabaseHandles:
    metadata: MetaData
    engine: Engine
    from_core: bool


def database_handles(data_dir: Path | None = None) -> DatabaseHandles:
    """默认使用核心 engine；测试可显式传入独立 engine。"""
    return DatabaseHandles(metadata=Base.metadata, engine=core_engine, from_core=True)

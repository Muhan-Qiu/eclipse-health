"""数据库底座。

这是 B1-02（模块系统）唯一依赖的共享文件，接口保持稳定：

- ``Base``：所有表模型的声明式基类（SQLModel）。
- ``engine``：进程内唯一 SQLAlchemy 引擎，SQLite 位于 ``EH_DATA_DIR``。
- ``get_session``：FastAPI 依赖，产出一个 ``Session``。
- ``init_db``：幂等建表 + 记录迁移版本。

模块侧只导入这几项，不要绕过 ``get_session`` 直接操作 engine。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from ..settings import get_settings

logger = logging.getLogger(__name__)


class Base(SQLModel):
    """共享声明式基类；子类加 ``table=True`` 即成为表。"""


_settings = get_settings()
_settings.ensure_dirs()

engine = create_engine(
    f"sqlite:///{_settings.db_path.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30.0},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


# (version, description)；只为记录「这个库走到哪一步」，不引入 Alembic。
CORE_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("0001_core", "members / records / signals / analyses / measurements / annotations / reports"),
)

MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：``session: Session = Depends(get_session)``。"""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台任务/启动逻辑用的事务上下文。"""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def init_db() -> None:
    """幂等初始化：建迁移表 → 建所有已注册的表 → 记录迁移版本。

    B1-02 的表模型只要在调用前被导入（注册进 ``Base.metadata``）就会被一并创建。
    """
    from . import models  # noqa: F401  导入即注册表模型

    with engine.begin() as connection:
        connection.execute(text(MIGRATIONS_TABLE_SQL))

    Base.metadata.create_all(engine)

    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        for version, description in CORE_MIGRATIONS:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO schema_migrations (version, description, applied_at) "
                    "VALUES (:version, :description, :applied_at)"
                ),
                {"version": version, "description": description, "applied_at": now},
            )


def reset_db() -> None:
    """删表重建。仅用于测试与显式「重置数据目录」场景。"""
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
    init_db()


def applied_migrations() -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
        return [row[0] for row in rows]


__all__ = [
    "CORE_MIGRATIONS",
    "Base",
    "applied_migrations",
    "engine",
    "get_session",
    "init_db",
    "reset_db",
    "session_scope",
]

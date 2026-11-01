"""OHS 测试夹具：每个用例独立清理 ``ohs.json`` 与数据库。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from eclipse_health_backend.api.errors import install_error_handlers
from eclipse_health_backend.db.base import reset_db, session_scope
from eclipse_health_backend.db.repositories import ensure_default_member
from eclipse_health_backend.ohs import store
from eclipse_health_backend.ohs.api import router


def dpapi_available() -> bool:
    try:
        import win32crypt  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


requires_dpapi = pytest.mark.skipif(
    not dpapi_available(), reason="Windows DPAPI is required"
)


@pytest.fixture()
def clean_ohs() -> Iterator[None]:
    store.config_path().unlink(missing_ok=True)
    yield
    store.config_path().unlink(missing_ok=True)


@pytest.fixture()
def session() -> Iterator[Session]:
    reset_db()
    with session_scope() as db_session:
        ensure_default_member(db_session)
        yield db_session


@pytest.fixture()
def api_client(clean_ohs: None) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    reset_db()
    with TestClient(app) as test_client:
        with session_scope() as db_session:
            ensure_default_member(db_session)
        yield test_client

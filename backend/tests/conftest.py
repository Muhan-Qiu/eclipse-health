"""全局测试夹具：临时数据目录 + 每例重建数据库。

必须在导入 ``eclipse_health_backend`` 之前设置 ``EH_DATA_DIR``，
因为引擎与设置都在导入时创建；真实 ``backend/.data`` 不会被触碰。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP_DATA_DIR = Path(tempfile.mkdtemp(prefix="eh-tests-"))
os.environ["EH_DATA_DIR"] = str(_TMP_DATA_DIR)
os.environ["EH_LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient

from eclipse_health_backend.app import app
from eclipse_health_backend.db.base import reset_db, session_scope
from eclipse_health_backend.db.repositories import ensure_default_member


@pytest.fixture(scope="session", autouse=True)
def _session_temp_dir() -> Iterator[Path]:
    yield _TMP_DATA_DIR
    shutil.rmtree(_TMP_DATA_DIR, ignore_errors=True)


@pytest.fixture()
def data_dir(_session_temp_dir: Path) -> Path:
    return _session_temp_dir


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        reset_db()
        with session_scope() as session:
            ensure_default_member(session)
        yield test_client


@pytest.fixture()
def default_member(client: TestClient) -> dict:
    response = client.get("/api/v1/members")
    assert response.status_code == 200, response.text
    members = response.json()
    assert members, "default member should exist"
    return members[0]

"""外部 API 测试夹具：provider 文件隔离、按 scope 创建 key。"""

from __future__ import annotations

from pathlib import Path

import pytest
from external_helpers import TEST_PROVIDER_ID
from fastapi.testclient import TestClient

from eclipse_health_backend.settings import get_settings


@pytest.fixture()
def providers_file() -> Path:
    path = get_settings().data_dir / "secrets" / "providers.json"
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture()
def make_key(client: TestClient):
    def _make(scopes: tuple[str, ...] = ("read", "write", "assistant"), name: str = "test"):
        response = client.post(
            "/api/v1/external/keys",
            json={"name": name, "scopes": list(scopes)},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture()
def read_key(make_key) -> dict:
    return make_key(("read",), "read-only")


@pytest.fixture()
def write_key(make_key) -> dict:
    return make_key(("read", "write"), "read-write")


@pytest.fixture()
def assistant_key(make_key) -> dict:
    return make_key(("read", "assistant"), "assistant")


@pytest.fixture()
def mock_provider(client: TestClient, providers_file: Path) -> dict:
    response = client.put(
        f"/api/v1/assistant/providers/{TEST_PROVIDER_ID}",
        json={"kind": "mock", "label": "Mock", "model": "mock-1"},
    )
    assert response.status_code == 200, response.text
    return response.json()

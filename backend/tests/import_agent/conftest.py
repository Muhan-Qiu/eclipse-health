"""导入 Agent 测试夹具：provider 隔离 + 默认 CSV 会话。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from import_agent_helpers import CSV_PULSE, upload_session

from eclipse_health_backend.settings import get_settings

MOCK_PROVIDER_ID = "llm_import_mock"


@pytest.fixture()
def providers_file() -> Path:
    path = get_settings().data_dir / "secrets" / "providers.json"
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture()
def mock_provider(client: TestClient, providers_file: Path) -> dict:
    response = client.put(
        f"/api/v1/assistant/providers/{MOCK_PROVIDER_ID}",
        json={"kind": "mock", "label": "Import Mock", "model": "mock-1"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def csv_session(client: TestClient, providers_file: Path) -> dict:
    return upload_session(client, {"pulse.csv": CSV_PULSE})

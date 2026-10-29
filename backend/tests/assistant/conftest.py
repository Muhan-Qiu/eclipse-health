"""助手测试夹具：每个用例前后清空 provider 配置，避免跨用例串味。"""

from __future__ import annotations

from pathlib import Path

import pytest
from assistant_helpers import MOCK_PROVIDER_ID, create_record, seed_analysis
from fastapi.testclient import TestClient

from eclipse_health_backend.settings import get_settings


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
        json={"kind": "mock", "label": "Mock", "model": "mock-1"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def record_with_analysis(client: TestClient, default_member: dict) -> dict:
    record = create_record(client, default_member["id"], notes="这是不应外传的备注")
    analysis_id = seed_analysis(record["id"])
    return {"record": record, "analysisId": analysis_id}


@pytest.fixture()
def empty_record(client: TestClient, default_member: dict) -> dict:
    return create_record(client, default_member["id"], notes="")

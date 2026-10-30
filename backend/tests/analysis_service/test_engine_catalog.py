"""C7 引擎注册表：目录 API、未知引擎校验、完成后的重新分析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from analysis_service_helpers import create_ecg_record, make_sine, wait_for_analysis
from fastapi.testclient import TestClient

from eclipse_health_backend.analysis_service import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    get_engine,
)


def test_engine_catalog_lists_cardia(client: TestClient) -> None:
    response = client.get("/api/v1/analyses/engines")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    cardia = items[0]
    assert cardia["id"] == CARDIA_ENGINE
    assert cardia["name"]
    assert cardia["moduleId"] == CARDIA_MODULE_ID
    assert cardia["modelId"] == CARDIA_MODEL_ID
    assert cardia["modelVersion"] == CARDIA_MODEL_VERSION
    assert cardia["available"] is True
    assert cardia["reason"] is None


def test_catalog_route_is_not_shadowed_by_analysis_id(client: TestClient) -> None:
    """``/analyses/engines`` 必须命中目录，而不是被 ``/analyses/{id}`` 吞掉。"""
    response = client.get("/api/v1/analyses/engines")
    assert response.status_code == 200
    assert "items" in response.json()
    missing = client.get("/api/v1/analyses/engnone")
    assert missing.status_code == 404
    assert missing.json()["code"] == "analysis_not_found"


def test_unknown_engine_is_rejected_with_registry_supported(
    client: TestClient, default_member: dict, direct_service: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine())
    response = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": "other"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unknown_engine"
    assert body["details"]["supported"] == [CARDIA_ENGINE]


def test_reanalyze_after_completion_creates_new_analysis(
    client: TestClient, default_member: dict, direct_service: Any, fake_analyze: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine())

    first = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": CARDIA_ENGINE}
    )
    assert first.status_code == 202, first.text
    first_body = first.json()
    assert first_body["engine"] == CARDIA_ENGINE
    assert wait_for_analysis(client, first_body["analysisId"])["status"] == "completed"

    second = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": CARDIA_ENGINE}
    )
    assert second.status_code == 202, second.text
    second_body = second.json()
    assert second_body["analysisId"] != first_body["analysisId"]
    assert second_body["engine"] == CARDIA_ENGINE
    assert second_body["status"] in {"queued", "running"}


def test_unavailable_engine_reports_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import eclipse_health_backend.analysis_service.engines as engines_module

    monkeypatch.setattr(engines_module, "CARDIA_SOURCE_DIR", tmp_path)
    descriptor = get_engine(CARDIA_ENGINE)
    assert descriptor is not None
    assert descriptor.available is False
    assert descriptor.reason


def test_get_engine_unknown_returns_none() -> None:
    assert get_engine("not-a-real-engine") is None

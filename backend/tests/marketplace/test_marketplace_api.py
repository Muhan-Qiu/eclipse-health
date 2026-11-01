"""REST 路由：索引、来源、安装、更新、错误体。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from marketplace_test_helpers import FakeManager, local_market, write_public_key

from eclipse_health_backend.marketplace import api as marketplace_api
from eclipse_health_backend.marketplace.service import MarketplaceService


@pytest.fixture()
def api_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(marketplace_api.router, prefix="/api/v1/marketplace")
    with TestClient(app) as client:
        yield client


def _use_service(monkeypatch: pytest.MonkeyPatch, service: MarketplaceService) -> None:
    monkeypatch.setattr(marketplace_api, "get_service", lambda: service)


def test_sources_reports_configuration(
    api_client: TestClient, tmp_path: Path, key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_path = write_public_key(tmp_path / "public_key.txt", key)
    monkeypatch.setenv("EH_MARKETPLACE_OFFICIAL_URL", "https://market.example.org/official/index.json")
    monkeypatch.setenv("EH_MARKETPLACE_COMMUNITY_URL", "")
    monkeypatch.setenv("EH_MARKETPLACE_PUBLIC_KEY", str(key_path))

    payload = api_client.get("/api/v1/marketplace/sources").json()

    assert payload["official"]["configured"] is True
    assert payload["official"]["url"].startswith("https://")
    assert payload["community"] == {"url": None, "configured": False}
    assert payload["keyIds"] == ["test-2026"]


def test_index_filters_and_community_unverified(
    api_client: TestClient, tmp_path: Path, key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    official_config, _item, _package = local_market(tmp_path, key)
    _use_service(
        monkeypatch, MarketplaceService(FakeManager(), config=official_config)
    )

    response = api_client.get(
        "/api/v1/marketplace/index", params={"source": "official", "q": "demo"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["keyId"] == "test-2026"
    assert payload["modules"][0]["verified"] is True

    community_config, _item, _package = local_market(
        tmp_path, key, source="community", module_id="io.github.example.community"
    )
    _use_service(
        monkeypatch, MarketplaceService(FakeManager(), config=community_config)
    )
    community = api_client.get(
        "/api/v1/marketplace/index", params={"source": "community"}
    ).json()
    assert community["modules"][0]["verified"] is False


def test_invalid_source_returns_422(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/marketplace/index", params={"source": "magic"})

    assert response.status_code == 422
    assert response.json()["code"] == "marketplace_source_invalid"


def test_not_configured_returns_503(
    api_client: TestClient, tmp_path: Path, key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eclipse_health_backend.marketplace.config import MarketplaceConfig

    key_path = write_public_key(tmp_path / "public_key.txt", key)
    config = MarketplaceConfig(None, None, key_path)
    _use_service(monkeypatch, MarketplaceService(FakeManager(), config=config))

    response = api_client.get("/api/v1/marketplace/index", params={"source": "official"})

    assert response.status_code == 503
    assert response.json()["code"] == "marketplace_not_configured"


def test_install_and_updates_endpoints(
    api_client: TestClient, tmp_path: Path, key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, item, _package = local_market(tmp_path, key)
    manager = FakeManager([{"id": item["id"], "version": "0.0.9"}])
    _use_service(monkeypatch, MarketplaceService(manager, config=config))

    installed = api_client.post(
        "/api/v1/marketplace/install",
        json={"source": "official", "moduleId": item["id"], "version": item["version"]},
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["moduleId"] == item["id"]

    updates = api_client.get("/api/v1/marketplace/updates")
    assert updates.status_code == 200
    assert updates.json()["count"] == 1
    assert updates.json()["updates"][0]["latestVersion"] == "0.1.0"

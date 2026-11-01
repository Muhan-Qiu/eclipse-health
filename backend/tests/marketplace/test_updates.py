"""更新检查：版本比较、官方优先、未安装过滤、社区索引。"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from marketplace_test_helpers import (
    FakeManager,
    build_index,
    entry,
    local_market,
    write_json,
    write_public_key,
)

from eclipse_health_backend.marketplace.config import MarketplaceConfig
from eclipse_health_backend.marketplace.service import MarketplaceService


def _config_for(
    tmp_path: Path, key: Ed25519PrivateKey, *, official: str = "0.2.0"
) -> MarketplaceConfig:
    official_path = write_json(
        tmp_path / "official" / "index.json",
        build_index([entry(version=official, size=16)], key),
    )
    community_path = write_json(
        tmp_path / "community" / "index.json",
        build_index(
            [entry(version="0.3.0", size=16, verified=True)], key, source="community"
        ),
    )
    key_path = tmp_path / "public_key.txt"
    write_public_key(key_path, key)
    return MarketplaceConfig(official_path.as_uri(), community_path.as_uri(), key_path)


def test_update_available(tmp_path: Path, key: Ed25519PrivateKey) -> None:
    config = _config_for(tmp_path, key)
    manager = FakeManager([{"id": "io.github.example.demo", "version": "0.1.0"}])

    payload = MarketplaceService(manager, config=config).updates()

    assert payload["count"] == 1
    update = payload["updates"][0]
    assert update["installedVersion"] == "0.1.0"
    assert update["latestVersion"] == "0.2.0"
    assert update["source"] == "official"


def test_up_to_date_returns_empty(tmp_path: Path, key: Ed25519PrivateKey) -> None:
    config = _config_for(tmp_path, key)
    manager = FakeManager([{"id": "io.github.example.demo", "version": "0.2.0"}])

    assert MarketplaceService(manager, config=config).updates()["updates"] == []


def test_module_not_installed_is_ignored(tmp_path: Path, key: Ed25519PrivateKey) -> None:
    config = _config_for(tmp_path, key)
    manager = FakeManager([])

    assert MarketplaceService(manager, config=config).updates()["count"] == 0


def test_official_index_wins_over_community(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _config_for(tmp_path, key, official="0.2.0")
    manager = FakeManager([{"id": "io.github.example.demo", "version": "0.1.0"}])

    payload = MarketplaceService(manager, config=config).updates()

    assert len(payload["updates"]) == 1
    assert payload["updates"][0]["source"] == "official"
    assert payload["updates"][0]["latestVersion"] == "0.2.0"


def test_community_update_is_unverified(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    community_config, item, _package = local_market(
        tmp_path, key, source="community", version="0.4.0"
    )
    manager = FakeManager([{"id": item["id"], "version": "0.1.0"}])

    payload = MarketplaceService(manager, config=community_config).updates()

    assert payload["count"] == 1
    assert payload["updates"][0]["source"] == "community"
    assert payload["updates"][0]["verified"] is False

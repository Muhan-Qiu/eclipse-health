"""索引读取、验签、条目校验、缓存与未配置行为。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from marketplace_test_helpers import build_index, entry, write_json

from eclipse_health_backend.marketplace.config import MarketplaceConfig
from eclipse_health_backend.marketplace.errors import MarketplaceError
from eclipse_health_backend.marketplace.index import fetch_index, reset_cache


def _config(index_path: Path, key_path: Path, *, source: str = "official") -> MarketplaceConfig:
    if source == "official":
        return MarketplaceConfig(index_path.as_uri(), None, key_path)
    return MarketplaceConfig(None, index_path.as_uri(), key_path)


def test_official_index_verifies_and_filters(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    modules = [
        entry(module_id="io.github.example.alpha", categories=["analysis"]),
        entry(
            module_id="io.github.example.beta",
            categories=["ui"],
            module_type="dashboard-widget",
            name="Beta Widget",
        ),
    ]
    index_path = write_json(tmp_path / "official" / "index.json", build_index(modules, key))

    index = fetch_index("official", _config(index_path, key_path))

    assert index.source == "official"
    assert index.key_id == "test-2026"
    assert len(index.modules) == 2
    assert all(item.verified for item in index.modules)

    filtered = [
        item.id for item in index.modules if "ui" in item.categories
    ]
    assert filtered == ["io.github.example.beta"]


def test_tampered_index_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    index = build_index([entry()], key)
    index["modules"][0]["name"] = "Tampered"
    index_path = write_json(tmp_path / "official" / "index.json", index)

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", _config(index_path, key_path))

    assert excinfo.value.code == "marketplace_signature_invalid"
    assert excinfo.value.http_status == 502


def test_missing_signature_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    index = build_index([entry()], key)
    index.pop("signature")
    index_path = write_json(tmp_path / "official" / "index.json", index)

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", _config(index_path, key_path))

    assert excinfo.value.code == "marketplace_signature_invalid"


def test_unknown_key_id_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    index = build_index([entry()], key, key_id="other-2026")
    index_path = write_json(tmp_path / "official" / "index.json", index)

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", _config(index_path, key_path))

    assert excinfo.value.code == "marketplace_signature_invalid"
    assert excinfo.value.detail == {"keyId": "other-2026"}


def test_community_entries_are_never_verified(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    modules = [entry(verified=True)]
    index_path = write_json(
        tmp_path / "community" / "index.json", build_index(modules, key, source="community")
    )

    index = fetch_index("community", _config(index_path, key_path, source="community"))

    assert index.source == "community"
    assert index.modules[0].verified is False


@pytest.mark.parametrize(
    "override",
    [
        {"version": "1.0"},
        {"minCoreVersion": "latest"},
        {"sha256": "ABC"},
        {"size": 0},
        {"id": "../escape"},
        {"file": "modules/../../evil.ehmod"},
    ],
)
def test_invalid_entry_fields_are_rejected(
    tmp_path: Path,
    key: Ed25519PrivateKey,
    key_path: Path,
    override: dict,
) -> None:
    index_path = write_json(
        tmp_path / "official" / "index.json", build_index([entry(**override)], key)
    )

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", _config(index_path, key_path))

    assert excinfo.value.code == "marketplace_index_invalid"


def test_duplicate_module_version_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    index_path = write_json(
        tmp_path / "official" / "index.json", build_index([entry(), entry()], key)
    )

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", _config(index_path, key_path))

    assert excinfo.value.code == "marketplace_index_invalid"


def test_not_configured_returns_marketplace_not_configured(key_path: Path) -> None:
    config = MarketplaceConfig(official_url=None, community_url=None, public_key_path=key_path)

    with pytest.raises(MarketplaceError) as excinfo:
        fetch_index("official", config)

    assert excinfo.value.code == "marketplace_not_configured"


def test_index_is_cached_for_ten_minutes(
    tmp_path: Path, key: Ed25519PrivateKey, key_path: Path
) -> None:
    index_path = write_json(tmp_path / "official" / "index.json", build_index([entry()], key))
    config = _config(index_path, key_path)
    assert fetch_index("official", config).modules[0].name == "Demo Module"

    tampered = build_index([entry()], key)
    tampered["modules"][0]["name"] = "Tampered"
    index_path.write_text(json.dumps(tampered), encoding="utf-8")

    # 缓存命中时不重新解析文件。
    assert fetch_index("official", config).modules[0].name == "Demo Module"
    reset_cache()
    with pytest.raises(MarketplaceError):
        fetch_index("official", config)

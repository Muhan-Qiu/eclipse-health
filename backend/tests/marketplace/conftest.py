"""Marketplace 测试夹具：每个用例独立签名密钥与索引缓存。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from marketplace_test_helpers import write_public_key

from eclipse_health_backend.marketplace.index import reset_cache


@pytest.fixture(autouse=True)
def _isolated_marketplace_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (
        "EH_MARKETPLACE_OFFICIAL_URL",
        "EH_MARKETPLACE_COMMUNITY_URL",
        "EH_MARKETPLACE_PUBLIC_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_cache()
    yield
    reset_cache()


@pytest.fixture()
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture()
def key_path(tmp_path: Path, key: Ed25519PrivateKey) -> Path:
    return write_public_key(tmp_path / "public_key.txt", key)

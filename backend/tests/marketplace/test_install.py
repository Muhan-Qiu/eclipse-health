"""下载、校验、临时文件清理、URL 安全策略与安装调用 manager。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
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
from eclipse_health_backend.marketplace.errors import MarketplaceError
from eclipse_health_backend.marketplace.service import MarketplaceService


def _market_with(
    tmp_path: Path,
    key: Ed25519PrivateKey,
    *,
    data: bytes,
    sha256: str | None = None,
    size: int | None = None,
    file: str = "modules/demo.ehmod",
    min_core_version: str = "0.1.0",
) -> MarketplaceConfig:
    root = tmp_path / "marketplace" / "official"
    package = root / "modules" / "demo.ehmod"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_bytes(data)
    item = entry(
        file=file,
        size=len(data) if size is None else size,
        sha256=hashlib.sha256(data).hexdigest() if sha256 is None else sha256,
        minCoreVersion=min_core_version,
    )
    write_json(root / "index.json", build_index([item], key))
    key_path = tmp_path / "public_key.txt"
    write_public_key(key_path, key)
    return MarketplaceConfig(root.joinpath("index.json").as_uri(), None, key_path)


def test_install_downloads_verifies_and_calls_manager(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config, item, _package = local_market(tmp_path, key)
    manager = FakeManager()
    result = MarketplaceService(manager, config=config).install(
        "official", item["id"], item["version"]
    )

    assert manager.calls[0]["enable"] is False
    assert manager.calls[0]["exists"] is True
    # 临时 .ehmod 在 manager 返回后必须被清理。
    assert not manager.calls[0]["path"].exists()
    assert result["version"] == "0.1.0"
    assert result["keyId"] == "test-2026"
    assert result["module"]["id"] == "io.github.example.demo"


def test_latest_version_is_selected_when_omitted(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    data = b"fake-ehmod-payload"
    root = tmp_path / "marketplace" / "official"
    (root / "modules").mkdir(parents=True)
    digest = hashlib.sha256(data).hexdigest()
    (root / "modules" / "io.github.example.demo-0.2.0.ehmod").write_bytes(data)
    modules = [
        entry(
            version="0.1.0",
            file="modules/io.github.example.demo-0.1.0.ehmod",
            size=len(data),
            sha256=digest,
        ),
        entry(
            version="0.2.0",
            file="modules/io.github.example.demo-0.2.0.ehmod",
            size=len(data),
            sha256=digest,
        ),
    ]
    index_path = write_json(root / "index.json", build_index(modules, key))
    key_path = write_public_key(tmp_path / "public_key.txt", key)
    config = MarketplaceConfig(index_path.as_uri(), None, key_path)

    manager = FakeManager()
    result = MarketplaceService(manager, config=config).install(
        "official", "io.github.example.demo"
    )
    assert result["version"] == "0.2.0"


def test_sha256_mismatch_fails_before_manager(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(tmp_path, key, data=b"payload", sha256="b" * 64)
    manager = FakeManager()

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(manager, config=config).install("official", "io.github.example.demo")

    assert excinfo.value.code == "marketplace_checksum_mismatch"
    assert manager.calls == []


def test_size_mismatch_fails_before_manager(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(tmp_path, key, data=b"payload", size=999)
    manager = FakeManager()

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(manager, config=config).install("official", "io.github.example.demo")

    assert excinfo.value.code == "marketplace_checksum_mismatch"
    assert manager.calls == []


def test_traversal_path_is_rejected_at_index_validation(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(
        tmp_path, key, data=b"payload", file="modules/../../evil.ehmod"
    )
    manager = FakeManager()

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(manager, config=config).install("official", "io.github.example.demo")

    assert excinfo.value.code == "marketplace_index_invalid"
    assert manager.calls == []


def test_unknown_version_returns_module_not_found(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config, _item, _package = local_market(tmp_path, key)

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(FakeManager(), config=config).install(
            "official", "io.github.example.demo", "9.9.9"
        )

    assert excinfo.value.code == "marketplace_module_not_found"


def test_incompatible_min_core_version_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(tmp_path, key, data=b"payload", min_core_version="99.0.0")

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(FakeManager(), config=config).install(
            "official", "io.github.example.demo"
        )

    assert excinfo.value.code == "marketplace_incompatible_core"


def test_http_download_to_localhost_is_allowed(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    payload = b"remote-ehmod"
    config = _market_with(
        tmp_path,
        key,
        data=payload,
        file="http://localhost:8765/demo.ehmod",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    manager = FakeManager()
    MarketplaceService(manager, config=config, client_factory=factory).install(
        "official", "io.github.example.demo"
    )
    assert manager.calls[0]["exists"] is True


def test_non_loopback_http_url_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(
        tmp_path, key, data=b"payload", file="http://example.com/demo.ehmod"
    )

    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(FakeManager(), config=config).install(
            "official", "io.github.example.demo"
        )

    assert excinfo.value.code == "marketplace_download_url_rejected"


def test_redirect_to_private_network_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(
        tmp_path, key, data=b"payload", file="https://cdn.example.com/demo.ehmod"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://192.168.1.9/demo.ehmod"})

    factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(FakeManager(), config=config, client_factory=factory).install(
            "official", "io.github.example.demo"
        )

    assert excinfo.value.code == "marketplace_download_url_rejected"


def test_oversize_content_length_is_rejected(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    config = _market_with(
        tmp_path, key, data=b"payload", file="https://cdn.example.com/demo.ehmod"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": str(200 * 1024 * 1024)})

    factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MarketplaceError) as excinfo:
        MarketplaceService(FakeManager(), config=config, client_factory=factory).install(
            "official", "io.github.example.demo"
        )

    assert excinfo.value.code == "marketplace_resource_exceeded"

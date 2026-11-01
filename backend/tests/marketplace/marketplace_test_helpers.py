"""Marketplace test helpers: Ed25519 test key, signed indexes, local artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from eclipse_health_backend.marketplace.config import MarketplaceConfig

KEY_ID = "test-2026"


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign(payload: dict[str, Any], key: Ed25519PrivateKey, *, key_id: str = KEY_ID) -> dict:
    body = {name: value for name, value in payload.items() if name != "signature"}
    body["keyId"] = key_id
    body["signature"] = base64.b64encode(key.sign(canonical(body))).decode("ascii")
    return body


def build_index(
    modules: list[dict[str, Any]],
    key: Ed25519PrivateKey,
    *,
    source: str = "official",
    key_id: str = KEY_ID,
    schema_version: str = "1",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": schema_version,
        "source": source,
        "generatedAt": "2026-11-01T00:00:00Z",
        "keyId": key_id,
        "modules": modules,
    }
    return sign(payload, key, key_id=key_id)


def entry(
    *,
    module_id: str = "io.github.example.demo",
    version: str = "0.1.0",
    file: str = "modules/io.github.example.demo-0.1.0.ehmod",
    size: int = 16,
    sha256: str | None = None,
    categories: list[str] | None = None,
    verified: bool = True,
    module_type: str = "analysis-model",
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": module_id,
        "name": "Demo Module",
        "version": version,
        "type": module_type,
        "description": "A demo module for marketplace tests",
        "author": "example",
        "license": "MIT",
        "repository": "https://github.com/example/demo",
        "permissions": ["records:read"],
        "dependencies": [],
        "minCoreVersion": "0.1.0",
        "categories": categories if categories is not None else ["analysis"],
        "verified": verified,
        "file": file,
        "size": size,
        "sha256": sha256 or "a" * 64,
    }
    payload.update(overrides)
    return payload


def write_public_key(path: Path, key: Ed25519PrivateKey, *, key_id: str = KEY_ID) -> Path:
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    path.write_text(f"keyId={key_id}\n{pem}", encoding="utf-8")
    return path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def local_market(
    tmp_path: Path,
    key: Ed25519PrivateKey,
    *,
    data: bytes = b"fake-ehmod-payload",
    source: str = "official",
    module_id: str = "io.github.example.demo",
    version: str = "0.1.0",
    description: str = "A demo module for marketplace tests",
) -> tuple[MarketplaceConfig, dict[str, Any], Path]:
    """Create <tmp>/marketplace/<source>/index.json plus modules/<pkg>.ehmod."""
    root = tmp_path / "marketplace" / source
    package = root / "modules" / f"{module_id}-{version}.ehmod"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_bytes(data)
    item = entry(
        module_id=module_id,
        version=version,
        file=f"modules/{package.name}",
        size=len(data),
        sha256=sha256_bytes(data),
        description=description,
        verified=source == "official",
    )
    index = build_index([item], key, source=source)
    index_path = write_json(root / "index.json", index)
    key_path = tmp_path / "public_key.txt"
    if not key_path.is_file():
        write_public_key(key_path, key)
    if source == "official":
        config = MarketplaceConfig(
            official_url=index_path.as_uri(),
            community_url=None,
            public_key_path=key_path,
        )
    else:
        config = MarketplaceConfig(
            official_url=None,
            community_url=index_path.as_uri(),
            public_key_path=key_path,
        )
    return config, item, package


class FakeManager:
    """只记录 install 调用的最小心智模型；不需要真实 SQLite。"""

    def __init__(
        self,
        installed: list[dict[str, Any]] | None = None,
        *,
        engine: Any = None,
        install_error: Exception | None = None,
    ) -> None:
        self.installed = installed or []
        self.engine = engine
        self.install_error = install_error
        self.calls: list[dict[str, Any]] = []

    def list_modules(self) -> list[dict[str, Any]]:
        return list(self.installed)

    def install(self, path: str | Path, *, enable: bool = False) -> dict[str, Any]:
        target = Path(path)
        self.calls.append({"path": target, "exists": target.is_file(), "enable": enable})
        if self.install_error is not None:
            raise self.install_error
        return {"id": "io.github.example.demo", "version": "0.1.0", "enabled": enable}


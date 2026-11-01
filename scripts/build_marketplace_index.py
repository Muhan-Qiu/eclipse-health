#!/usr/bin/env python3
"""Build and sign the official/community marketplace indexes (H8).

Reads ``dist/modules/index.json`` + every ``modules/official/*/module.json``,
optionally ``marketplace/community/*.json``, then writes:

    marketplace/official/index.json
    marketplace/community/index.json
    backend/src/eclipse_health_backend/marketplace/public_key.txt

The Ed25519 private key lives in ``.secrets/marketplace_ed25519.key`` (gitignored).
If it does not exist, a development key is generated so the app can boot locally.
Production signing is an offline step; use ``scripts/sign_marketplace_index.py``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = ROOT / ".secrets" / "marketplace_ed25519.key"
DEFAULT_PUBLIC_KEY = (
    ROOT / "backend" / "src" / "eclipse_health_backend" / "marketplace" / "public_key.txt"
)
BUNDLED_MODULE_IDS = frozenset({"org.eclipsehealth.cardia"})
DEFAULT_KEY_ID = "dev-2026"

TYPE_CATEGORY = {
    "device-adapter": "devices",
    "signal-engine": "signal",
    "analysis-model": "analysis",
    "health-domain": "health",
    "dashboard-widget": "ui",
    "exporter": "export",
    "ai-tool": "ai",
    "theme": "theme",
    "locale": "locale",
    "data-source": "data",
}
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def author_name(author: object) -> str:
    if isinstance(author, dict):
        return str(author.get("name") or "")
    return str(author or "")


def min_core_version(manifest: dict) -> str:
    engines = manifest.get("engines") or {}
    constraint = str(engines.get("eclipse") or "")
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", constraint)
    if not match:
        return "0.1.0"
    major, minor, patch = match.group(1), match.group(2), match.group(3) or "0"
    return f"{major}.{minor}.{patch}"


def artifact_for(module_id: str, version: str, dist_dir: Path) -> Path | None:
    candidate = dist_dir / f"{module_id}-{version}.ehmod"
    return candidate if candidate.is_file() else None


def packed_artifacts(pack_index: Path, dist_dir: Path) -> dict[str, tuple[str, Path]]:
    """Read pack_official_modules.py's index so a stale version is never reused."""
    if not pack_index.is_file():
        return {}
    raw = load_json(pack_index)
    if not isinstance(raw, dict):
        return {}
    result: dict[str, tuple[str, Path]] = {}
    for item in raw.get("modules") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        name = Path(str(item.get("file") or "")).name
        if name and (dist_dir / name).is_file():
            result[str(item["id"])] = (
                str(item.get("version") or ""),
                dist_dir / name,
            )
    return result


def official_entries(official_dir: Path, dist_dir: Path, pack_index: Path) -> list[dict]:
    packed = packed_artifacts(pack_index, dist_dir)
    entries: list[dict] = []
    failures: list[str] = []
    for manifest_path in sorted(official_dir.glob("*/module.json")):
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{manifest_path}: {exc}")
            continue
        if not isinstance(manifest, dict):
            failures.append(f"{manifest_path}: manifest must be an object")
            continue
        module_id = str(manifest.get("id") or "")
        version = str(manifest.get("version") or "")
        if module_id in BUNDLED_MODULE_IDS:
            continue
        if not module_id or not SEMVER_RE.match(version):
            failures.append(f"{manifest_path}: invalid id/version")
            continue
        artifact = artifact_for(module_id, version, dist_dir)
        packed_item = packed.get(module_id)
        if artifact is None and packed_item is not None and packed_item[0] == version:
            artifact = packed_item[1]
        if artifact is None:
            failures.append(
                f"{module_id}: missing .ehmod in {dist_dir} (run pack_official_modules.py)"
            )
            continue
        module_type = str(manifest.get("type") or "")
        entries.append(
            {
                "id": module_id,
                "name": str(manifest.get("name") or module_id),
                "version": version,
                "type": module_type,
                "description": str(manifest.get("description") or ""),
                "author": author_name(manifest.get("author")),
                "license": str(manifest.get("license") or ""),
                "repository": str(manifest.get("repository") or ""),
                "permissions": list(manifest.get("permissions") or []),
                "dependencies": list(manifest.get("dependencies") or []),
                "minCoreVersion": min_core_version(manifest),
                "categories": [TYPE_CATEGORY.get(module_type, "other")],
                "verified": True,
                "file": f"modules/{artifact.name}",
                "size": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    if failures:
        print("error: cannot build official index:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        raise SystemExit(1)
    return entries


def community_entries(
    community_modules_dir: Path, dist_dir: Path, pack_index: Path
) -> list[dict]:
    """社区索引直接扫描 ``modules/community/*/module.json``，一律 verified=false。"""
    packed = packed_artifacts(pack_index, dist_dir)
    entries: list[dict] = []
    failures: list[str] = []
    for manifest_path in sorted(community_modules_dir.glob("*/module.json")):
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{manifest_path}: {exc}")
            continue
        if not isinstance(manifest, dict):
            failures.append(f"{manifest_path}: manifest must be an object")
            continue
        module_id = str(manifest.get("id") or "")
        version = str(manifest.get("version") or "")
        if not module_id or not SEMVER_RE.match(version):
            failures.append(f"{manifest_path}: invalid id/version")
            continue
        artifact = artifact_for(module_id, version, dist_dir)
        packed_item = packed.get(module_id)
        if artifact is None and packed_item is not None and packed_item[0] == version:
            artifact = packed_item[1]
        if artifact is None:
            failures.append(
                f"{module_id}: missing .ehmod in {dist_dir} (run pack_official_modules.py)"
            )
            continue
        module_type = str(manifest.get("type") or "")
        entries.append(
            {
                "id": module_id,
                "name": str(manifest.get("name") or module_id),
                "version": version,
                "type": module_type,
                "description": str(manifest.get("description") or ""),
                "author": author_name(manifest.get("author")),
                "license": str(manifest.get("license") or ""),
                "repository": str(manifest.get("repository") or ""),
                "permissions": list(manifest.get("permissions") or []),
                "dependencies": list(manifest.get("dependencies") or []),
                "minCoreVersion": min_core_version(manifest),
                "categories": [TYPE_CATEGORY.get(module_type, "other")],
                "verified": False,
                "file": f"modules/{artifact.name}",
                "size": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    if failures:
        print("error: cannot build community index:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        raise SystemExit(1)
    return entries


def load_private_key(path: Path):
    raw = path.read_bytes()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    text = raw.strip()
    if text.startswith(b"-----BEGIN"):
        return load_pem_private_key(raw, password=None)
    if len(text) == 64 and re.fullmatch(rb"[0-9a-fA-F]{64}", text):
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(text.decode("ascii")))
    if len(raw) == 32:
        return Ed25519PrivateKey.from_private_bytes(raw)
    raise SystemExit(f"error: unsupported private key format: {path}")


def load_or_create_key(path: Path):
    if path.is_file():
        return load_private_key(path)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"generated development key: {path} (gitignored; replace for production)")
    return key


def public_pem(key) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def write_public_key(path: Path, key_id: str, pem: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# eclipse health marketplace public keys\n"
        "# keyId -> Ed25519 public key (PEM), used by the desktop app to verify indexes\n"
        f"keyId={key_id}\n"
        f"{pem.rstrip()}\n",
        encoding="utf-8",
    )
    print(f"public key: {path} (keyId={key_id})")


def write_index(
    source: str,
    modules: list[dict],
    output: Path,
    key,
    key_id: str,
) -> dict:
    modules.sort(key=lambda item: (item["id"], item["version"]))
    ids = [(item["id"], item["version"]) for item in modules]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"error: duplicate module id/version in {source} index")
    payload: dict = {
        "schemaVersion": "1",
        "source": source,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "keyId": key_id,
        "modules": modules,
    }
    signature = key.sign(canonical_bytes(payload))
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{source}: {len(modules)} module(s) -> {output}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--official-dir", type=Path, default=ROOT / "modules" / "official"
    )
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist" / "modules")
    parser.add_argument(
        "--pack-index", type=Path, default=ROOT / "dist" / "modules" / "index.json"
    )
    parser.add_argument(
        "--community-modules-dir",
        type=Path,
        default=ROOT / "modules" / "community",
        help="社区模块源码目录；索引从这里扫描 */module.json",
    )
    parser.add_argument(
        "--official-out",
        type=Path,
        default=ROOT / "marketplace" / "official" / "index.json",
    )
    parser.add_argument(
        "--community-out",
        type=Path,
        default=ROOT / "marketplace" / "community" / "index.json",
    )
    parser.add_argument("--key", type=Path, default=None)
    parser.add_argument("--key-id", default=os.environ.get("EH_MARKETPLACE_KEY_ID", DEFAULT_KEY_ID))
    parser.add_argument("--public-key-out", type=Path, default=DEFAULT_PUBLIC_KEY)
    args = parser.parse_args(argv)

    key_path = args.key or DEFAULT_KEY
    if not key_path.is_absolute():
        key_path = ROOT / key_path
    key = load_or_create_key(key_path)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", args.key_id):
        raise SystemExit("error: --key-id must match [A-Za-z0-9._-]{1,64}")

    official = official_entries(args.official_dir, args.dist_dir, args.pack_index)
    community = community_entries(
        args.community_modules_dir, args.dist_dir, args.pack_index
    )
    if not official:
        raise SystemExit("error: no official modules found; run pack_official_modules.py first")

    write_index("official", official, args.official_out, key, args.key_id)
    write_index("community", community, args.community_out, key, args.key_id)
    write_public_key(args.public_key_out, args.key_id, public_pem(key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fallback builder for marketplace/official|community/index.json.

The preferred implementation is `scripts/build_marketplace_index.py` (H8).
The publish workflow calls that script when present and falls back to this
file in checkouts where it has not landed yet. Both produce the same shape:

    {schemaVersion, source, generatedAt, keyId, modules[], signature}

This script never generates a key. Without an explicit key it emits an
unsigned index and says so; production signing is an offline maintainer step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
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


def min_core_version(manifest: dict) -> str:
    engines = manifest.get("engines") or {}
    constraint = str(engines.get("eclipse") or "")
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", constraint)
    if not match:
        return "0.1.0"
    return f"{match.group(1)}.{match.group(2)}.{match.group(3) or '0'}"


def author_name(author: object) -> str:
    if isinstance(author, dict):
        return str(author.get("name") or "")
    return str(author or "")


def artifact_for(module_id: str, version: str, dist_dir: Path, marketplace_root: Path) -> Path | None:
    name = f"{module_id}-{version}.ehmod"
    for candidate in (
        dist_dir / name,
        marketplace_root / "modules" / name,
        marketplace_root / "submissions" / module_id / name,
    ):
        if candidate.is_file():
            return candidate
    return None


def official_entries(
    official_dir: Path,
    dist_dir: Path,
    pack_index: Path,
    marketplace_root: Path,
) -> list[dict]:
    pack: dict[str, dict] = {}
    if pack_index.is_file():
        raw = load_json(pack_index)
        if isinstance(raw, dict) and isinstance(raw.get("modules"), list):
            pack = {
                str(item.get("id")): item
                for item in raw["modules"]
                if isinstance(item, dict) and item.get("id")
            }

    entries: list[dict] = []
    if official_dir.is_dir():
        for manifest_path in sorted(official_dir.glob("*/module.json")):
            manifest = load_json(manifest_path)
            if not isinstance(manifest, dict):
                continue
            module_id = str(manifest.get("id") or "")
            version = str(manifest.get("version") or "")
            if not module_id or not SEMVER_RE.match(version):
                raise SystemExit(f"error: invalid manifest {manifest_path}")
            artifact = artifact_for(module_id, version, dist_dir, marketplace_root)
            packed = pack.get(module_id)
            if artifact is None:
                if packed and packed.get("file"):
                    artifact = dist_dir / Path(str(packed["file"])).name
                if artifact is None or not artifact.is_file():
                    # Cardia ships inside the installer and is not a marketplace
                    # download; pack_official_modules.py skips it deliberately.
                    if packed is None:
                        print(f"WARNING: skipping bundled module without package: {module_id}")
                        continue
                    raise SystemExit(
                        f"error: missing .ehmod for {module_id} {version}; run pack_official_modules.py"
                    )
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
    return entries


def iter_community_documents(community_dir: Path) -> list[dict]:
    items: list[dict] = []
    if not community_dir.is_dir():
        return items
    for path in sorted(community_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"error: cannot read {path}: {exc}") from exc
        if isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict) and isinstance(data.get("modules"), list):
            items.extend(item for item in data["modules"] if isinstance(item, dict))
        elif isinstance(data, dict) and data.get("id"):
            items.append(data)
    return items


def community_entries(community_dir: Path, dist_dir: Path, marketplace_root: Path) -> list[dict]:
    entries: list[dict] = []
    for raw in iter_community_documents(community_dir):
        module_id = str(raw.get("id") or "")
        version = str(raw.get("version") or raw.get("latest") or "")
        if not module_id or not SEMVER_RE.match(version):
            raise SystemExit(f"error: community entry has invalid id/version: {module_id!r} {version!r}")
        artifact = artifact_for(module_id, version, dist_dir, marketplace_root)
        if artifact is None and raw.get("file"):
            candidate = marketplace_root / str(raw["file"])
            if candidate.is_file():
                artifact = candidate
        size = raw.get("size")
        digest = raw.get("sha256")
        if artifact is not None:
            size = artifact.stat().st_size
            digest = sha256_file(artifact)
            file_value = f"modules/{artifact.name}"
        else:
            file_value = str(raw.get("file") or f"modules/{module_id}-{version}.ehmod")
        if not digest or not SHA256_RE.match(str(digest)):
            raise SystemExit(f"error: community entry {module_id} has no valid sha256")
        module_type = str(raw.get("type") or "")
        categories = raw.get("categories")
        if not isinstance(categories, list) or not categories:
            categories = [TYPE_CATEGORY.get(module_type, "other")]
        entries.append(
            {
                "id": module_id,
                "name": str(raw.get("name") or module_id),
                "version": version,
                "type": module_type,
                "description": str(raw.get("description") or raw.get("summary") or ""),
                "author": author_name(raw.get("author")),
                "license": str(raw.get("license") or ""),
                "repository": str(raw.get("repository") or ""),
                "permissions": list(raw.get("permissions") or []),
                "dependencies": list(raw.get("dependencies") or []),
                "minCoreVersion": str(raw.get("minCoreVersion") or "0.1.0"),
                "categories": [str(item) for item in categories],
                "verified": False,
                "file": file_value,
                "size": int(size or 0),
                "sha256": str(digest),
            }
        )
    return entries


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_signing_key(args: argparse.Namespace):
    raw: bytes | None = None
    if args.key:
        path = Path(args.key)
        if path.is_file():
            raw = path.read_bytes()
        else:
            raise SystemExit(f"error: signing key not found: {path}")
    elif os.environ.get("EH_MARKETPLACE_ED25519_KEY"):
        value = os.environ["EH_MARKETPLACE_ED25519_KEY"].strip()
        if "BEGIN" in value:
            raw = value.replace("\\n", "\n").encode("utf-8")
        elif re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raw = bytes.fromhex(value)
        else:
            raise SystemExit("error: EH_MARKETPLACE_ED25519_KEY must be PEM or 64 hex chars")
    if raw is None:
        return None
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError as exc:
        raise SystemExit("error: signing requires `pip install cryptography`") from exc
    try:
        return load_pem_private_key(raw, password=None)
    except ValueError:
        if len(raw) == 32:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )

            return Ed25519PrivateKey.from_private_bytes(raw)
        raise


def write_index(
    source: str,
    modules: list[dict],
    output: Path,
    key,
    key_id: str,
    unsigned: bool,
) -> dict:
    modules.sort(key=lambda item: item["id"])
    ids = [item["id"] for item in modules]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"error: duplicate module id in {source} index")
    payload: dict = {
        "schemaVersion": "1",
        "source": source,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "keyId": key_id,
        "modules": modules,
        "signature": None,
    }
    if key is not None and not unsigned:
        import base64

        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        signature = key.sign(canonical_bytes(payload))
        payload["signature"] = base64.b64encode(signature).decode("ascii")
        public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        print(f"{source}: signed with {key_id} ({len(modules)} modules)")
        print(public.decode("ascii"))
    else:
        print(f"WARNING: {source}: unsigned index (production signing is offline)")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{source}: {len(modules)} module(s) -> {output}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-dir", type=Path, default=ROOT / "modules" / "official")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist" / "modules")
    parser.add_argument("--pack-index", type=Path, default=ROOT / "dist" / "modules" / "index.json")
    parser.add_argument("--community-dir", type=Path, default=ROOT / "marketplace" / "community")
    parser.add_argument("--marketplace-root", type=Path, default=ROOT / "marketplace")
    parser.add_argument("--official-out", type=Path, default=ROOT / "marketplace" / "official" / "index.json")
    parser.add_argument("--community-out", type=Path, default=ROOT / "marketplace" / "community" / "index.json")
    parser.add_argument("--key", default=os.environ.get("EH_MARKETPLACE_KEY", ""))
    parser.add_argument("--key-id", default=os.environ.get("EH_MARKETPLACE_KEY_ID", "dev-unsafe"))
    parser.add_argument("--unsigned", action="store_true", help="force unsigned output even if a key is present")
    parser.add_argument("--dry-run", action="store_true", help="build in memory but do not write files")
    args = parser.parse_args(argv)

    key = None if args.unsigned else load_signing_key(args)
    official = official_entries(args.official_dir, args.dist_dir, args.pack_index, args.marketplace_root)
    community = community_entries(args.community_dir, args.dist_dir, args.marketplace_root)
    has_manifests = args.official_dir.is_dir() and any(args.official_dir.glob("*/module.json"))
    if has_manifests and not official:
        raise SystemExit(
            "error: official modules exist but no .ehmod packages were found; "
            "run scripts/pack_official_modules.py before building the index"
        )
    if args.dry_run:
        print(json.dumps({"official": official, "community": community}, ensure_ascii=False, indent=2))
        return 0
    write_index("official", official, args.official_out, key, args.key_id, args.unsigned)
    write_index("community", community, args.community_out, key, args.key_id, args.unsigned)
    return 0


if __name__ == "__main__":
    sys.exit(main())

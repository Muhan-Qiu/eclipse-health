#!/usr/bin/env python3
"""Re-sign an existing marketplace index with an offline Ed25519 key.

Production flow: build the index, then sign it on a machine that holds the
private key. The app matches ``keyId`` against its built-in public key table.

Usage:
    backend\\.venv\\Scripts\\python.exe scripts\\sign_marketplace_index.py ^
      --key .secrets\\marketplace_ed25519.key ^
      --index marketplace\\official\\index.json
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = ROOT / ".secrets" / "marketplace_ed25519.key"


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def load_private_key(path: Path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    raw = path.read_bytes()
    stripped = raw.strip()
    if stripped.startswith(b"-----BEGIN"):
        return load_pem_private_key(raw, password=None)
    if len(stripped) == 64 and re.fullmatch(rb"[0-9a-fA-F]{64}", stripped):
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(stripped.decode("ascii")))
    if len(raw) == 32:
        return Ed25519PrivateKey.from_private_bytes(raw)
    raise SystemExit(f"error: unsupported private key format: {path}")


def public_pem(key) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def sign_index(path: Path, key, key_id: str | None) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict) or "modules" not in payload:
        raise SystemExit(f"error: {path} does not look like an index")
    resolved_key_id = key_id or str(payload.get("keyId") or "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", resolved_key_id):
        raise SystemExit("error: --key-id must match [A-Za-z0-9._-]{1,64}")
    body = {name: value for name, value in payload.items() if name != "signature"}
    body["keyId"] = resolved_key_id
    body["signature"] = base64.b64encode(key.sign(canonical_bytes(body))).decode("ascii")
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"signed: {path} (keyId={resolved_key_id})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, action="append", required=True)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--key-id", default=None)
    parser.add_argument(
        "--public-key-out",
        type=Path,
        default=None,
        help="optional: rewrite the app's public key table after signing",
    )
    args = parser.parse_args(argv)

    key_path = args.key if args.key.is_absolute() else ROOT / args.key
    if not key_path.is_file():
        raise SystemExit(f"error: signing key not found: {key_path}")
    key = load_private_key(key_path)

    for index_path in args.index:
        sign_index(index_path if index_path.is_absolute() else ROOT / index_path, key, args.key_id)

    pem = public_pem(key)
    print(pem.rstrip())
    if args.public_key_out is not None:
        key_id = args.key_id or "dev-2026"
        output = (
            args.public_key_out
            if args.public_key_out.is_absolute()
            else ROOT / args.public_key_out
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "# eclipse health marketplace public keys\n"
            f"keyId={key_id}\n"
            f"{pem.rstrip()}\n",
            encoding="utf-8",
        )
        print(f"public key: {output} (keyId={key_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

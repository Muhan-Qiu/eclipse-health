#!/usr/bin/env python3
"""Pack `modules/official/*` into `dist/modules/*.ehmod` for CI index builds.

This is a stdlib-only equivalent of `scripts/pack_official_modules.py` so the
publish workflow does not need the full backend dependency tree. It never
mutates the source tree: checksums are written into a temporary staging copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules"}
BUNDLED = {"org.eclipsehealth.cardia"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(directory: Path) -> None:
    files: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts):
            continue
        if relative.as_posix() == "checksums.json":
            continue
        files[relative.as_posix()] = sha256_file(path)
    (directory / "checksums.json").write_text(
        json.dumps({"algorithm": "sha256", "files": files}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pack(source: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts):
                continue
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "modules" / "official")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "modules")
    args = parser.parse_args(argv)

    if not args.source.is_dir():
        print(f"error: {args.source} not found", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="eh-pack-") as temp_dir:
        for manifest_path in sorted(args.source.glob("*/module.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            module_id = str(manifest.get("id") or "")
            version = str(manifest.get("version") or "")
            if not module_id or not version:
                print(f"error: invalid manifest {manifest_path}", file=sys.stderr)
                return 1
            if module_id in BUNDLED:
                continue
            entry_path = str((manifest.get("entry") or {}).get("python") or "")
            source_dir = manifest_path.parent
            if not (source_dir / "src").is_dir():
                print(f"error: {source_dir} has no src/ directory", file=sys.stderr)
                return 1
            if not entry_path or not (source_dir / entry_path).is_file():
                print(f"error: {source_dir} entry.python is missing", file=sys.stderr)
                return 1
            staging = Path(temp_dir) / module_id
            shutil.copytree(
                manifest_path.parent,
                staging,
                ignore=shutil.ignore_patterns(*SKIP_DIRS, "checksums.json", "*.ehmod", "*.pyc"),
            )
            write_checksums(staging)
            filename = f"{module_id}-{version}.ehmod"
            output = args.out / filename
            pack(staging, output)
            entries.append(
                {
                    "id": module_id,
                    "name": str(manifest.get("name") or module_id),
                    "version": version,
                    "type": str(manifest.get("type") or ""),
                    "description": str(manifest.get("description") or ""),
                    "license": str(manifest.get("license") or ""),
                    "repository": str(manifest.get("repository") or ""),
                    "permissions": list(manifest.get("permissions") or []),
                    "dependencies": list(manifest.get("dependencies") or []),
                    "file": filename,
                    "size": output.stat().st_size,
                    "sha256": sha256_file(output),
                }
            )
    index = {
        "schemaVersion": "1",
        "generatedBy": ".github/scripts/pack_official_modules.py",
        "modules": entries,
    }
    (args.out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"packed: {len(entries)} modules -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

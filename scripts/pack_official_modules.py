"""Pack every module under modules/official into .ehmod and build a catalog index.

Usage (project root):
    backend\\.venv\\Scripts\\python.exe scripts\\pack_official_modules.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "backend" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eclipse_health_backend.modules import package
from eclipse_health_backend.modules.manifest import load_manifest_file

OFFICIAL = ROOT / "modules" / "official"
OUT = ROOT / "dist" / "modules"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not OFFICIAL.is_dir():
        print(f"error: {OFFICIAL} not found", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    failures: list[str] = []

    for source in sorted(p for p in OFFICIAL.iterdir() if p.is_dir()):
        manifest_path = source / "module.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest_file(manifest_path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{source.name}: {exc}")
            continue
        if manifest.id == "org.eclipsehealth.cardia":
            continue  # bundled separately
        shutil.rmtree(source / "__pycache__", ignore_errors=True)
        package.write_checksums(source)
        filename = f"{manifest.id}-{manifest.version}.ehmod"
        output = OUT / filename
        package.pack_directory(source, output)
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted = Path(temp_dir) / "verify"
            with zipfile.ZipFile(output) as zf:
                package.extract_package(zf, extracted)
            package.verify_checksums(extracted)
            package.verify_layout(extracted, load_manifest_file(extracted / "module.json"))
        entries.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type.value,
                "description": manifest.description,
                "license": manifest.license,
                "repository": manifest.repository,
                "permissions": list(manifest.permissions),
                "dependencies": list(manifest.dependencies),
                "file": filename,
                "size": output.stat().st_size,
                "sha256": _sha256(output),
            }
        )

    index = {
        "schemaVersion": "1",
        "generatedBy": "scripts/pack_official_modules.py",
        "modules": entries,
    }
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"packed: {len(entries)} modules -> {OUT}")
    print(f"index: {OUT / 'index.json'}")
    if failures:
        print("failures:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""打包 modules/official/cardia 为 .ehmod（官方 Cardia 分析模块）。

会先重写模块目录下的 `checksums.json`（它是提交物），再打包并自校验。

用法（项目根目录）：
    backend\\.venv\\Scripts\\python.exe scripts\\pack_cardia.py
"""

from __future__ import annotations

import argparse
import hashlib
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

CARDIA_DIR = ROOT / "modules" / "official" / "cardia"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack the official Cardia module")
    parser.add_argument("--out", type=Path, default=None, help="output .ehmod path")
    parser.add_argument("--module-dir", type=Path, default=CARDIA_DIR)
    args = parser.parse_args()

    module_dir = args.module_dir.resolve()
    manifest_path = module_dir / "module.json"
    if not manifest_path.is_file():
        print(f"error: {manifest_path} not found", file=sys.stderr)
        return 2

    manifest = load_manifest_file(manifest_path)
    for cached in module_dir.rglob("__pycache__"):
        for item in cached.rglob("*"):
            if item.is_file():
                item.unlink()
        cached.rmdir()
    package.write_checksums(module_dir)

    output = args.out or (ROOT / "dist" / f"cardia-{manifest.version}.ehmod")
    output = output.resolve()
    package.pack_directory(module_dir, output)

    with tempfile.TemporaryDirectory() as temp_dir:
        extracted = Path(temp_dir) / "verify"
        with zipfile.ZipFile(output) as zf:
            package.extract_package(zf, extracted)
        package.verify_checksums(extracted)
        package.verify_layout(extracted, load_manifest_file(extracted / "module.json"))

    with zipfile.ZipFile(output) as zf:
        file_count = sum(1 for info in zf.infolist() if not info.is_dir())

    print(f"packed: {output}")
    print(f"sha256: {_sha256(output)}")
    print(f"files: {file_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

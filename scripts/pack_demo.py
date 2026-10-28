"""打包 modules/demo.echo 为 .ehmod（模块内核全链路演示用）。

用法（项目根目录）：
    backend\\.venv\\Scripts\\python.exe scripts\\pack_demo.py
"""

from __future__ import annotations

import argparse
import hashlib
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

DEMO_DIR = ROOT / "modules" / "demo.echo"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack the demo.echo module into an .ehmod")
    parser.add_argument("--out", type=Path, default=None, help="output .ehmod path")
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR, help="module source directory")
    args = parser.parse_args()

    demo_dir = args.demo_dir.resolve()
    manifest_path = demo_dir / "module.json"
    if not manifest_path.is_file():
        print(f"error: {manifest_path} not found", file=sys.stderr)
        return 2

    manifest = load_manifest_file(manifest_path)
    shutil.rmtree(demo_dir / "__pycache__", ignore_errors=True)
    package.write_checksums(demo_dir)

    output = args.out or (ROOT / "dist" / f"demo.echo-{manifest.version}.ehmod")
    output = output.resolve()
    package.pack_directory(demo_dir, output)

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

"""测试辅助：按需改写并重打包 demo 模块、构造任意 ZIP。"""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

from eclipse_health_backend.modules.package import pack_directory, write_checksums

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "modules" / "demo.echo"
DEMO_ID = "org.eclipsehealth.demo.echo"


def build_demo_package(
    tmp_path: Path,
    *,
    version: str = "1.0.0",
    permissions: list[str] | None = None,
    manifest_updates: dict | None = None,
    mutate: Callable[[Path], None] | None = None,
    checksums: bool = True,
) -> Path:
    """从 modules/demo.echo 复制一份并按需改写，产出 .ehmod。"""
    token = uuid.uuid4().hex[:8]
    source = tmp_path / f"demo-src-{token}"
    shutil.copytree(DEMO_DIR, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest_path = source / "module.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    if permissions is not None:
        manifest["permissions"] = permissions
    if manifest_updates:
        manifest.update(manifest_updates)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if mutate is not None:
        mutate(source)
    if checksums:
        write_checksums(source)
    else:
        (source / "checksums.json").unlink(missing_ok=True)
    output = tmp_path / f"demo-{version}-{token}.ehmod"
    pack_directory(source, output)
    return output


def build_zip(tmp_path: Path, entries: dict[str, bytes | str], name: str = "test.ehmod") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry_name, content in entries.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(entry_name, data)
    return path

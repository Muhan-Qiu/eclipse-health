"""Pack every module under modules/official and modules/community into .ehmod.

产物统一放在 ``dist/modules``，文件名保持 ``<module-id>-<version>.ehmod``，
因此官方/社区分家不会改变已安装模块的身份或下载地址。

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

MODULE_ROOTS = (
    ROOT / "modules" / "official",
    ROOT / "modules" / "community",
)
OUT = ROOT / "dist" / "modules"
RELAY_SLEEP_ID = "org.eclipsehealth.relay-sleep"
RELAY_SLEEP_WEIGHTS = ROOT / "uploads" / "relay-sleep" / "models"
RELAY_ECG_ID = "org.eclipsehealth.relay-ecg"
RELAY_ECG_WEIGHTS = ROOT / "uploads" / "relay-ecg" / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_relay_sleep(source: Path, staging: Path) -> int:
    """复制模块源码后把 uploads 里的大权重放进 staging/models，避免提交 git。"""
    shutil.copytree(
        source,
        staging,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.onnx"),
    )
    models_dir = staging / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    if RELAY_SLEEP_WEIGHTS.is_dir():
        for weight in sorted(RELAY_SLEEP_WEIGHTS.glob("*.onnx")):
            shutil.copy2(weight, models_dir / weight.name)
            copied += 1
    if copied == 0:
        print(
            f"warning: {RELAY_SLEEP_ID} 没有可用权重，"
            f"请在 {RELAY_SLEEP_WEIGHTS} 放置 *.onnx",
            file=sys.stderr,
        )
    return copied


def _stage_relay_ecg(source: Path, staging: Path) -> int:
    """把 relay-ecg 的 7 个 ONNX 从 uploads 复制进 staging/models；权重不进 git。"""
    shutil.copytree(
        source,
        staging,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.onnx"),
    )
    models_dir = staging / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    if RELAY_ECG_WEIGHTS.is_dir():
        for weight in sorted(RELAY_ECG_WEIGHTS.glob("*.onnx")):
            shutil.copy2(weight, models_dir / weight.name)
            copied += 1
    if copied != 7:
        print(
            f"warning: {RELAY_ECG_ID} 应有 7 个 ONNX 权重，实际 {copied}，"
            f"请先运行 tools/export_onnx.py（{RELAY_ECG_WEIGHTS}）",
            file=sys.stderr,
        )
    return copied


def main() -> int:
    roots = [root for root in MODULE_ROOTS if root.is_dir()]
    if not roots:
        print(f"error: none of {MODULE_ROOTS} found", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    failures: list[str] = []
    seen_ids: dict[str, str] = {}

    for modules_root in roots:
        for source in sorted(p for p in modules_root.iterdir() if p.is_dir()):
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
            if manifest.id in seen_ids:
                failures.append(
                    f"{source.name}: duplicate id {manifest.id} "
                    f"(also in {seen_ids[manifest.id]})"
                )
                continue
            seen_ids[manifest.id] = modules_root.name
            filename = f"{manifest.id}-{manifest.version}.ehmod"
            output = OUT / filename
            with tempfile.TemporaryDirectory(prefix=f"ehmod-{source.name}-") as stage_dir:
                if manifest.id == RELAY_SLEEP_ID:
                    pack_source = Path(stage_dir) / "staging"
                    _stage_relay_sleep(source, pack_source)
                elif manifest.id == RELAY_ECG_ID:
                    pack_source = Path(stage_dir) / "staging"
                    _stage_relay_ecg(source, pack_source)
                else:
                    pack_source = source
                    shutil.rmtree(source / "__pycache__", ignore_errors=True)
                package.write_checksums(pack_source)
                package.pack_directory(pack_source, output)
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
                    "source": modules_root.name,
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

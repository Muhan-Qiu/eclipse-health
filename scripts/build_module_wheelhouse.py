#!/usr/bin/env python
"""构建模块依赖的离线 wheel 仓库（随安装包分发）。

背景
----
模块的 ``dependencies`` 过去只能在安装时从 PyPI 下载。国内网络、离线机器或代理环境
下 pip 会超时/失败，表现为「功能型模块安装不了」，而 UI 类模块（无依赖）正常。

本脚本在**构建机**上把官方模块（可选社区模块）的全部依赖解析成 wheel，放进
``backend/packaging/wheelhouse/``；PyInstaller 再把它打进 ``_internal/wheelhouse``。
安装版运行时就可用 ``pip --no-index --find-links`` 完全离线安装。

用法
----
    backend\\.venv\\Scripts\\python.exe scripts\\build_module_wheelhouse.py
    python scripts\\build_module_wheelhouse.py --include-community --verify

注意：wheel 与 Python ABI / 平台绑定。必须在与 sidecar 相同的 Python（3.12）和
Windows x64 构建机上运行。换 Python 小版本后需要重建。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = ROOT / "modules"
DEFAULT_OUTPUT = ROOT / "backend" / "packaging" / "wheelhouse"
TARGET_PYTHON = (3, 12)
REQUIREMENTS_FILE = "_requirements.txt"
INDEX_FILE = "index.json"


def _module_dirs(groups: list[str]) -> list[Path]:
    found: list[Path] = []
    for group in groups:
        base = MODULES_DIR / group
        if not base.is_dir():
            continue
        for manifest in sorted(base.glob("*/module.json")):
            found.append(manifest.parent)
    return found


def _manifest_data(module_dir: Path) -> dict[str, object]:
    try:
        data = json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"[warn] 跳过无法解析的 manifest: {module_dir} ({exc})")
        return {}
    return data if isinstance(data, dict) else {}


def collect_requirements(module_dirs: list[Path]) -> tuple[dict[str, list[str]], list[str]]:
    """返回 {moduleId: requirements} 与去重后的总需求列表。"""
    by_module: dict[str, list[str]] = {}
    ordered: list[str] = []
    seen: set[str] = set()
    for module_dir in module_dirs:
        data = _manifest_data(module_dir)
        module_id = str(data.get("id") or module_dir.name)
        deps = data.get("dependencies") or []
        if not isinstance(deps, list):
            continue
        cleaned = [str(item).strip() for item in deps if str(item).strip()]
        if not cleaned:
            continue
        by_module[module_id] = cleaned
        for dep in cleaned:
            if dep not in seen:
                seen.add(dep)
                ordered.append(dep)
    return by_module, ordered


def _run(args: list[str], *, timeout_s: float = 1800.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_wheels(python: str, requirements: list[str], output: Path) -> None:
    requirements_file = output / REQUIREMENTS_FILE
    requirements_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    command = [
        python,
        "-m",
        "pip",
        "wheel",
        "--prefer-binary",
        "--wheel-dir",
        str(output),
        "--requirement",
        str(requirements_file),
    ]
    print(f"[build] {' '.join(command)}")
    result = _run(command)
    if result.returncode != 0:
        tail = ((result.stdout or "") + (result.stderr or "")).strip()[-3000:]
        raise SystemExit(f"pip wheel 失败：\n{tail}")


def verify_offline(python: str, by_module: dict[str, list[str]], output: Path) -> list[str]:
    """逐个模块做 --no-index 依赖解析，确认离线仓库覆盖完整。"""
    failures: list[str] = []
    for module_id, deps in by_module.items():
        command = [
            python,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--ignore-installed",
            "--quiet",
            "--no-index",
            "--find-links",
            str(output),
            *deps,
        ]
        result = _run(command, timeout_s=300.0)
        if result.returncode != 0:
            tail = ((result.stdout or "") + (result.stderr or "")).strip()[-800:]
            failures.append(f"{module_id}: {tail}")
            print(f"[verify] FAIL {module_id}")
        else:
            print(f"[verify] ok   {module_id}")
    return failures


def write_index(
    output: Path, by_module: dict[str, list[str]], requirements: list[str]
) -> Path:
    wheels = {
        path.name: _sha256(path)
        for path in sorted(output.glob("*.whl"))
    }
    payload = {
        "schemaVersion": 1,
        "builtAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "modules": by_module,
        "requirements": requirements,
        "wheels": wheels,
    }
    index_path = output / INDEX_FILE
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return index_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="用于解析/构建 wheel 的 Python（默认当前解释器）",
    )
    parser.add_argument(
        "--include-community",
        action="store_true",
        help="同时收录 modules/community 的依赖（体积会明显变大）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="构建后用 --no-index 逐个模块验证离线可解析",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="保留输出目录里已有的 wheel（默认清空重建，避免 ABI 混杂）",
    )
    args = parser.parse_args()

    if sys.version_info[:2] != TARGET_PYTHON:
        print(
            f"[warn] 当前 Python {platform.python_version()}，"
            f"sidecar 目标为 {TARGET_PYTHON[0]}.{TARGET_PYTHON[1]}；"
            "wheel 可能不匹配。请用 backend/.venv 运行。"
        )

    groups = ["official"]
    if args.include_community:
        groups.append("community")
    module_dirs = _module_dirs(groups)
    by_module, requirements = collect_requirements(module_dirs)
    if not requirements:
        print("[error] 没有找到任何模块依赖")
        return 1

    output: Path = args.output
    if output.exists() and not args.keep:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    print(f"[info] 模块 {len(by_module)} 个，依赖声明 {len(requirements)} 条")
    build_wheels(args.python, requirements, output)

    index_path = write_index(output, by_module, requirements)
    total_mb = sum(path.stat().st_size for path in output.glob("*.whl")) / (1024 * 1024)
    print(f"[done] {len(list(output.glob('*.whl')))} wheels, {total_mb:.1f} MB -> {output}")
    print(f"[done] index -> {index_path}")

    if args.verify:
        failures = verify_offline(args.python, by_module, output)
        if failures:
            print("\n[verify] 以下模块离线依赖不完整：")
            for failure in failures:
                print(f"  - {failure}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

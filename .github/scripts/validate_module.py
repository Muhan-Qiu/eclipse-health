#!/usr/bin/env python3
"""Validate eclipse health marketplace submissions.

Checks, in order:
  1. `module.json` against `schemas/module.schema.json` (JSON Schema 2020-12).
  2. Repository policy: id namespace, license whitelist, LICENSE/NOTICE files.
  3. Pack safety: symlinks, traversal, file/size limits, obvious secrets.
  4. `.ehmod` packaging and re-opening: checksums, layout, entry point.

Usage:
    python .github/scripts/validate_module.py marketplace/submissions/my-module
    python .github/scripts/validate_module.py --all --actor someone --repo-owner someone

Exit code 0 only when every module passes. Errors block merge in CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

MAX_FILES = 10_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024

ALLOWED_LICENSES = {
    "MIT",
    "MIT-0",
    "ISC",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "MPL-2.0",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "Unlicense",
    "CC0-1.0",
    "Zlib",
    "BSL-1.0",
}

REJECTED_LICENSE_MARKERS = ("AGPL", "SSPL", "BUSL", "Commons-Clause", "LicenseRef", "UNLICENSED", "NOASSERTION")
NOTICE_LICENSES = {"Apache-2.0"}
FORBIDDEN_DIRS = {"venv", ".venv", "__pycache__", "node_modules", ".git", ".secrets", ".idea", ".vscode"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
CHECKSUM_NAME = "checksums.json"
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
SECRET_PATTERNS = (
    (re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key block"),
    (re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "GitHub token"),
    (re.compile(rb"\bsk-[A-Za-z0-9]{32,}\b"), "API secret key"),
)
DIAGNOSTIC_PATTERN = re.compile(r"诊断|治愈|治疗|替代医生|\bdiagnos|\bcure\b|\btreatment\b", re.IGNORECASE)
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)


class Result:
    def __init__(self, label: str) -> None:
        self.label = label
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.artifacts: list[Path] = []

    def error(self, message: str, path: Path | None = None) -> None:
        self.errors.append(f"{self._where(path)}{message}")

    def warning(self, message: str, path: Path | None = None) -> None:
        self.warnings.append(f"{self._where(path)}{message}")

    def _where(self, path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return f"{path.as_posix()}: "
        except Exception:  # noqa: BLE001 - best-effort display only
            return ""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(module_dir: Path, result: Result) -> list[Path]:
    files: list[Path] = []
    total = 0
    for path in sorted(module_dir.rglob("*")):
        relative = path.relative_to(module_dir)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            if path.is_dir():
                continue
            result.error("包内包含不应提交的目录（venv/.git/__pycache__ 等）", path)
            continue
        if path.is_symlink():
            result.error("不允许符号链接", path)
            continue
        if not path.is_file():
            continue
        files.append(path)
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            result.error(f"单文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MB", path)
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            result.error("提交中不得包含密钥或凭据文件", path)
        if size <= 2 * 1024 * 1024:
            try:
                payload = path.read_bytes()
            except OSError:
                payload = b""
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(payload):
                    result.error(f"疑似包含{label}，请移除后再提交", path)
                    break
    if len(files) > MAX_FILES:
        result.error(f"文件数超过 {MAX_FILES}")
    if total > MAX_TOTAL_BYTES:
        result.error(f"总大小超过 {MAX_TOTAL_BYTES // (1024 * 1024)} MB")
    return files


def validate_schema(manifest: dict, manifest_path: Path, schema_path: Path, result: Result) -> None:
    try:
        import jsonschema
    except ImportError:
        result.error("缺少 jsonschema：CI 需执行 `pip install jsonschema`")
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.error(f"无法读取 schema {schema_path}: {exc}")
        return
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    for error in errors[:20]:
        location = "/".join(str(part) for part in error.path) or "(根)"
        result.error(f"schema: {location}: {error.message}", manifest_path)
    if len(errors) > 20:
        result.error(f"schema: 另有 {len(errors) - 20} 个错误未显示", manifest_path)


def validate_license(manifest: dict, module_dir: Path, result: Result) -> None:
    license_id = str(manifest.get("license") or "").strip()
    if not license_id:
        result.error("license 不能为空")
        return
    upper = license_id.upper()
    if any(marker.upper() in upper for marker in REJECTED_LICENSE_MARKERS):
        result.error(f"许可证 {license_id} 不在白名单（AGPL/无许可证/专有许可禁止进入官方索引）")
        return
    if license_id not in ALLOWED_LICENSES:
        result.error(f"许可证 {license_id} 不在白名单内；允许集合见 marketplace/CONTRIBUTING.md")
        return
    license_files = [
        item for item in module_dir.iterdir()
        if item.is_file() and re.match(r"^(licen[cs]e|copying)(\.(md|txt|rst))?$", item.name, re.IGNORECASE)
    ]
    if not license_files:
        result.error("缺少 LICENSE 文件（完整许可证文本）")
    if license_id in NOTICE_LICENSES:
        notice_files = [
            item for item in module_dir.iterdir()
            if item.is_file() and re.match(r"^notice(\.(md|txt))?$", item.name, re.IGNORECASE)
        ]
        if not notice_files:
            result.error(f"许可证 {license_id} 要求 NOTICE 文件")


def validate_policy(manifest: dict, module_dir: Path, result: Result, actor: str, repo_owner: str, allow_official: bool) -> None:
    module_id = str(manifest.get("id") or "")
    if not allow_official and not module_id.startswith("io.github."):
        result.error("社区提交必须使用 io.github.<owner>.<name> 形式的 ID")
    if module_id.startswith("io.github."):
        parts = module_id.split(".")
        owner = parts[2].lower() if len(parts) > 2 else ""
        expected = {value.lower() for value in (actor, repo_owner) if value}
        if expected and owner not in expected:
            result.error(
                f"ID 中的 owner `{owner}` 与 PR 作者或仓库所有者不一致，"
                "社区模块必须绑定 GitHub 身份"
            )
    description = " ".join(
        str(manifest.get(key) or "") for key in ("name", "description")
    )
    if DIAGNOSTIC_PATTERN.search(description):
        result.warning("描述疑似包含诊断/治疗宣称；扫描器会标记为高风险，请改为非诊断表述")
    dependencies = manifest.get("dependencies") or []
    for dependency in dependencies:
        text = str(dependency)
        if "@" in text or text.strip().startswith(("-", ".", "/")) or "file:" in text or "git+" in text:
            result.error(f"依赖 `{text}` 使用了 URL/本地路径/editable 形式")
    if "network" in (manifest.get("permissions") or []):
        hosts = manifest.get("allowedHosts") or []
        if not hosts:
            result.error("声明 network 权限时必须提供非空 allowedHosts")
        for host in hosts:
            if "*" in str(host):
                result.error(f"allowedHosts 不允许通配符：{host}")
    entry = manifest.get("entry") or {}
    entry_path = entry.get("python")
    if entry_path:
        candidate = (module_dir / str(entry_path)).resolve()
        try:
            candidate.relative_to(module_dir.resolve())
        except ValueError:
            result.error("entry.python 指向模块目录之外")
        if not candidate.is_file():
            result.error("entry.python 指向的文件不存在", module_dir / str(entry_path))
    if not (module_dir / "src").is_dir():
        result.error("缺少 src/ 目录")
    if not (module_dir / "README.md").is_file():
        result.warning("建议提供 README.md（用法、权限、数据来源、非诊断声明）")


def write_checksums(module_dir: Path) -> None:
    files: dict[str, str] = {}
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file() or path.name == CHECKSUM_NAME:
            continue
        relative = path.relative_to(module_dir)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            continue
        files[relative.as_posix()] = sha256_file(path)
    payload = {"algorithm": "sha256", "files": files}
    (module_dir / CHECKSUM_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pack_directory(source_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir)
            if any(part in FORBIDDEN_DIRS for part in relative.parts):
                continue
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def safe_member_name(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return False
    normalized = name.replace("\\", "/")
    for part in normalized.split("/"):
        if part in {"", ".", ".."}:
            return False
        if ":" in part or part.endswith((" ", ".")):
            return False
        if part.split(".")[0].upper() in WINDOWS_RESERVED:
            return False
    return True


def validate_archive(archive_path: Path, expected: dict, result: Result) -> None:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        result.error(f".ehmod 无法解包：{exc}", archive_path)
        return
    with archive:
        names: list[str] = []
        total = 0
        for info in archive.infolist():
            if not safe_member_name(info.filename):
                result.error(f"包内路径不安全：{info.filename}", archive_path)
                continue
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                result.error(f"包内包含符号链接：{info.filename}", archive_path)
                continue
            if info.is_dir():
                continue
            names.append(info.filename)
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES:
                result.error(f"包内单文件超过限制：{info.filename}", archive_path)
        if len(names) > MAX_FILES or total > MAX_TOTAL_BYTES:
            result.error("包内文件数或解压体积超过限制", archive_path)
        if "module.json" not in names:
            result.error("包内缺少 module.json", archive_path)
            return
        try:
            inner_manifest = json.loads(archive.read("module.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            result.error(f"包内 module.json 不是合法 UTF-8 JSON：{exc}", archive_path)
            return
        if inner_manifest.get("id") != expected.get("id"):
            result.error("包内 manifest 的 id 与源码不一致", archive_path)
        if inner_manifest.get("version") != expected.get("version"):
            result.error("包内 manifest 的 version 与源码不一致", archive_path)
        if not any(name.startswith("src/") for name in names):
            result.error("包内缺少 src/ 目录", archive_path)
        if CHECKSUM_NAME in names:
            try:
                checksums = json.loads(archive.read(CHECKSUM_NAME).decode("utf-8"))
                files = checksums.get("files") if isinstance(checksums, dict) else None
                if not isinstance(files, dict):
                    result.error("checksums.json 缺少 files 映射", archive_path)
                else:
                    for name, digest in files.items():
                        if name not in names:
                            result.error(f"checksums.json 引用了不存在的文件：{name}", archive_path)
                            continue
                        actual = hashlib.sha256(archive.read(name)).hexdigest()
                        if actual != str(digest):
                            result.error(f"checksums 不匹配：{name}", archive_path)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                result.error(f"checksums.json 无法解析：{exc}", archive_path)
        else:
            result.warning("打包结果缺少 checksums.json（安装时只会降级为警告）", archive_path)


def validate_module(manifest_path: Path, args: argparse.Namespace, schema_path: Path, out_dir: Path) -> Result:
    result = Result(manifest_path.parent.name or str(manifest_path))
    module_dir = manifest_path.parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.error(f"module.json 无法解析：{exc}", manifest_path)
        return result
    if not isinstance(manifest, dict):
        result.error("module.json 顶层必须是对象", manifest_path)
        return result

    validate_schema(manifest, manifest_path, schema_path, result)
    validate_license(manifest, module_dir, result)
    validate_policy(manifest, module_dir, result, args.actor, args.repo_owner, args.allow_official)
    iter_files(module_dir, result)

    module_id = str(manifest.get("id") or "module")
    version = str(manifest.get("version") or "0.0.0")
    if not SEMVER_PATTERN.match(version):
        result.error("version 不是合法 SemVer", manifest_path)

    prebuilt = sorted(module_dir.glob("*.ehmod"))
    for archive in prebuilt:
        validate_archive(archive, manifest, result)

    try:
        with tempfile.TemporaryDirectory(prefix="ehmod-ci-") as temp_dir:
            staging = Path(temp_dir) / "stage"
            shutil.copytree(
                module_dir,
                staging,
                ignore=shutil.ignore_patterns(
                    *FORBIDDEN_DIRS, "*.ehmod", "checksums.json", "*.pyc"
                ),
            )
            write_checksums(staging)
            artifact = out_dir / f"{module_id}-{version}.ehmod"
            pack_directory(staging, artifact)
            validate_archive(artifact, manifest, result)
            result.artifacts.append(artifact)
    except OSError as exc:
        result.error(f"打包失败：{exc}")

    return result


def discover(paths: list[Path], scan_all: bool) -> list[Path]:
    if scan_all:
        paths = [repo_root() / "marketplace" / "submissions", repo_root() / "modules" / "community"]
    manifests: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file() and path.name == "module.json":
            manifests.append(path)
            continue
        if path.is_dir() and (path / "module.json").is_file():
            manifests.append(path / "module.json")
            continue
        if path.is_dir():
            for candidate in sorted(path.rglob("module.json")):
                relative = candidate.relative_to(path)
                if any(part in FORBIDDEN_DIRS for part in relative.parts):
                    continue
                if candidate.parent == path:
                    continue
                manifests.append(candidate)
    seen: set[Path] = set()
    unique: list[Path] = []
    for manifest in manifests:
        resolved = manifest.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(manifest)
    return unique


def emit(message: str, level: str, file: Path | None = None) -> None:
    prefix = {"error": "::error", "warning": "::warning"}.get(level, "")
    if os.environ.get("GITHUB_ACTIONS") and prefix:
        location = f" file={file.as_posix()}" if file else ""
        print(f"{prefix}{location}::{message}")
    else:
        print(f"{level.upper()}: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate eclipse health module submissions")
    parser.add_argument("paths", nargs="*", type=Path, help="module directory or module.json")
    parser.add_argument("--all", action="store_true", help="scan marketplace/submissions and modules/community")
    parser.add_argument("--schema", type=Path, default=repo_root() / "schemas" / "module.schema.json")
    parser.add_argument("--out", type=Path, default=repo_root() / "dist-ci", help="directory for built .ehmod files")
    parser.add_argument("--actor", default=os.environ.get("GITHUB_ACTOR", ""), help="PR author GitHub login")
    parser.add_argument("--repo-owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    parser.add_argument("--allow-official", action="store_true", help="allow org.eclipsehealth.* ids")
    args = parser.parse_args(argv)

    manifests = discover(args.paths, args.all)
    if not manifests:
        message = "没有找到 module.json；跳过（若这是首个提交，请放到 marketplace/submissions/<id>/）"
        emit(message, "warning")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(f"- {message}\n", encoding="utf-8")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    results = [validate_module(path, args, args.schema, args.out) for path in manifests]
    total_errors = 0
    total_warnings = 0
    summary: list[str] = ["| Module | Errors | Warnings | Artifact |", "| --- | --- | --- | --- |"]
    for manifest_path, result in zip(manifests, results):
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        for message in result.errors:
            emit(f"[{result.label}] {message}", "error", manifest_path)
        for message in result.warnings:
            emit(f"[{result.label}] {message}", "warning")
        artifact = ", ".join(path.name for path in result.artifacts) or "—"
        summary.append(f"| `{result.label}` | {len(result.errors)} | {len(result.warnings)} | {artifact} |")
        print(f"\n{result.label}: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
        for artifact in result.artifacts:
            print(f"  built {artifact}")
    print(f"\nvalidated {len(results)} module(s): {total_errors} error(s), {total_warnings} warning(s)")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        summary.append("")
        summary.append(f"**{len(results)} module(s) · {total_errors} error(s) · {total_warnings} warning(s)**")
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

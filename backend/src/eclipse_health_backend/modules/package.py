"""`.ehmod` 包解析：路径安全、大小限制、checksums 校验、原子解压与打包。"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .constants import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILE_BYTES,
    MAX_PACKAGE_FILES,
)
from .errors import ModuleError
from .manifest import Manifest

_CHECKSUM_ALGORITHM = "sha256"
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(slots=True)
class PackageMember:
    name: str
    archive_name: str
    is_dir: bool
    size: int


@dataclass(slots=True)
class ExtractionReport:
    files: int
    bytes: int
    warnings: list[str] = field(default_factory=list)


def _normalize_member_name(raw: str) -> str:
    if "\x00" in raw:
        raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包包含 NUL 字符路径")
    name = raw.replace("\\", "/")
    if not name or name.startswith(("/", "//")) or _DRIVE_RE.match(name):
        raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包包含绝对路径",
                          {"entry": _safe_display(raw)})
    segments = name.split("/")
    for segment in segments:
        if segment in {"", ".", ".."}:
            raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包包含路径穿越片段",
                              {"entry": _safe_display(raw)})
        # Windows 会把冒号解释为 NTFS 数据流，保留设备名会写到设备上。
        if ":" in segment or segment.endswith((" ", ".")):
            raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包路径在 Windows 上不安全",
                              {"entry": _safe_display(raw)})
        if segment.split(".")[0].upper() in _RESERVED_WINDOWS_NAMES:
            raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包使用了 Windows 保留设备名",
                              {"entry": _safe_display(raw)})
    if any(ord(char) < 32 for char in name):
        raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包路径包含控制字符")
    return name


def _safe_display(name: str) -> str:
    """用于错误详情，去掉可能泄露本地路径的部分。"""
    return name.replace("\\", "/")[-120:]


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return bool(mode) and stat.S_ISLNK(mode)


def scan_package(zf: zipfile.ZipFile) -> list[PackageMember]:
    members: list[PackageMember] = []
    seen: dict[str, str] = {}
    total = 0
    files = 0
    for info in zf.infolist():
        name = _normalize_member_name(info.filename)
        if _is_symlink(info):
            raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包包含符号链接",
                              {"entry": _safe_display(name)})
        key = name.rstrip("/").lower()
        if key in seen:
            raise ModuleError("INVALID_PACKAGE", "模块包包含重复路径",
                              {"entry": _safe_display(name)})
        seen[key] = name
        is_dir = info.is_dir() or name.endswith("/")
        if is_dir:
            members.append(PackageMember(name.rstrip("/"), info.filename, True, 0))
            continue
        files += 1
        if files > MAX_PACKAGE_FILES:
            raise ModuleError("RESOURCE_EXCEEDED", f"模块包文件数超过 {MAX_PACKAGE_FILES}")
        if info.file_size > MAX_PACKAGE_FILE_BYTES:
            raise ModuleError("RESOURCE_EXCEEDED", "模块包单个文件超过 64MB",
                              {"entry": _safe_display(name)})
        total += info.file_size
        if total > MAX_PACKAGE_BYTES:
            raise ModuleError("RESOURCE_EXCEEDED", "模块包解压后超过 256MB")
        members.append(PackageMember(name, info.filename, False, info.file_size))
    return members


def extract_package(zf: zipfile.ZipFile, destination: Path) -> ExtractionReport:
    """先扫描再解压，任何路径问题在写盘前拒绝。"""
    members = scan_package(zf)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    file_count = 0
    written = 0
    for member in members:
        if member.is_dir:
            (destination / member.name).mkdir(parents=True, exist_ok=True)
            continue
        target = (destination / member.name).resolve()
        if target != destination and destination not in target.parents:
            raise ModuleError("UNSAFE_PACKAGE_PATH", "模块包路径越界")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member.archive_name) as source, target.open("wb") as sink:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_PACKAGE_BYTES:
                    raise ModuleError("RESOURCE_EXCEEDED", "模块包解压后超过 256MB")
                sink.write(chunk)
        file_count += 1
    return ExtractionReport(files=file_count, bytes=written)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checksums(module_dir: Path) -> dict[str, str] | None:
    path = module_dir / "checksums.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModuleError("INVALID_PACKAGE", "checksums.json 不是合法 UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ModuleError("INVALID_PACKAGE", "checksums.json 顶层必须是对象")
    algorithm = raw.get("algorithm", _CHECKSUM_ALGORITHM)
    if algorithm != _CHECKSUM_ALGORITHM:
        raise ModuleError("INVALID_PACKAGE", f"不支持 checksums 算法 {algorithm}")
    files = raw.get("files", raw)
    if not isinstance(files, dict):
        raise ModuleError("INVALID_PACKAGE", "checksums.json 缺少 files 映射")
    checksums: dict[str, str] = {}
    for name, digest in files.items():
        if name == "algorithm":
            continue
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ModuleError("INVALID_PACKAGE", "checksums.json 条目必须是字符串")
        if not _is_safe_relative(name):
            raise ModuleError("UNSAFE_PACKAGE_PATH", "checksums.json 引用了不安全路径",
                              {"entry": _safe_display(name)})
        normalized = digest.strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ModuleError("INVALID_PACKAGE", "checksums.json 包含非法 sha256",
                              {"entry": _safe_display(name)})
        checksums[name.replace("\\", "/")] = normalized
    return checksums


def _is_safe_relative(name: str) -> bool:
    try:
        normalized = _normalize_member_name(name)
    except ModuleError:
        return False
    return normalized == name.replace("\\", "/")


def verify_checksums(module_dir: Path) -> list[str]:
    checksums = load_checksums(module_dir)
    if checksums is None:
        return ["checksums.json 缺失，已跳过完整性校验（B1 不强制）"]

    mismatches: list[str] = []
    for name, expected in checksums.items():
        target = module_dir / name
        if not target.is_file():
            mismatches.append(name)
            continue
        if sha256_file(target) != expected:
            mismatches.append(name)
    if mismatches:
        raise ModuleError(
            "CHECKSUM_MISMATCH",
            "模块包文件校验失败",
            {"files": [name[-120:] for name in sorted(mismatches)][:32]},
        )

    known = {member.relative_to(module_dir).as_posix() for member in module_dir.rglob("*") if member.is_file()}
    uncovered = sorted(known - set(checksums) - {"checksums.json"})
    warnings: list[str] = []
    if uncovered:
        warnings.append(f"checksums.json 未覆盖 {len(uncovered)} 个文件")
    return warnings


def verify_layout(module_dir: Path, manifest: Manifest) -> None:
    if not (module_dir / "module.json").is_file():
        raise ModuleError("INVALID_PACKAGE", "模块包缺少 module.json")
    source_root = module_dir / "src"
    if not source_root.is_dir():
        raise ModuleError("INVALID_PACKAGE", "模块包缺少 src/ 目录")
    entry = module_dir / manifest.entry_path
    if not entry.is_file():
        raise ModuleError("INVALID_PACKAGE", "manifest entry.python 指向的文件不存在",
                          {"entry": _safe_display(manifest.entry_path)})
    if module_dir.resolve() not in entry.resolve().parents:
        raise ModuleError("UNSAFE_PACKAGE_PATH", "manifest entry 指向模块目录之外")
    for locale, relative in manifest.i18n.items():
        if not (module_dir / relative).is_file():
            raise ModuleError("INVALID_PACKAGE", f"i18n 文件缺失（{locale}）",
                              {"entry": _safe_display(relative)})


def write_checksums(module_dir: Path) -> Path:
    files: dict[str, str] = {}
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(module_dir).as_posix()
        if relative == "checksums.json":
            continue
        files[relative] = sha256_file(path)
    payload = {"algorithm": _CHECKSUM_ALGORITHM, "files": files}
    target = module_dir / "checksums.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def pack_directory(source_dir: Path, output_path: Path) -> Path:
    """把模块目录打成 .ehmod；调用前应已写入 checksums.json。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    temp_path.replace(output_path)
    return output_path

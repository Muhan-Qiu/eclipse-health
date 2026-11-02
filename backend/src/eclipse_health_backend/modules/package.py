"""`.ehmod` 包解析：路径安全、大小限制、checksums 校验、原子解压与打包。

另含每模块独立 venv 的创建/依赖安装（模块依赖只装进该版本的 venv，不污染核心环境）。
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .constants import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILE_BYTES,
    MAX_PACKAGE_FILES,
)
from .errors import ModuleError
from .manifest import Manifest, validate_dependencies

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


# ---------------------------------------------------------------- 每模块 venv
MODULE_VENV_DIRNAME = "venv"
MODULE_DEPS_DIRNAME = "deps"
_DEPS_MARKER = ".deps-ready"
DEPENDENCY_INSTALL_TIMEOUT_S = 300.0
_MAX_LOG_CHARS = 4000
_READY_MARKER = ".ready"
_PATH_FILE = "eclipse_health_module.pth"


def dependency_digest(dependencies: Sequence[str]) -> str:
    """依赖列表的稳定 hash（与顺序无关），用于 .ready 与审计。"""
    normalized = validate_dependencies(dependencies)
    return hashlib.sha256("\n".join(sorted(normalized)).encode("utf-8")).hexdigest()


def module_venv_dir(module_dir: Path) -> Path:
    return module_dir / MODULE_VENV_DIRNAME


def module_deps_dir(module_dir: Path) -> Path:
    """冻结版 sidecar 没有独立 python.exe，依赖装进这个目录并加入 worker 的 sys.path。"""
    return module_dir / MODULE_DEPS_DIRNAME


def venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _site_packages_dir(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Lib" / "site-packages"
    matches = sorted((venv_dir / "lib").glob("python*/site-packages"))
    return matches[0] if matches else venv_dir / "lib" / "site-packages"


def remove_module_venv(module_dir: Path) -> None:
    """删除模块版本目录下的 venv/deps；不触碰模块文件或用户数据。"""
    shutil.rmtree(module_venv_dir(module_dir), ignore_errors=True)
    shutil.rmtree(module_deps_dir(module_dir), ignore_errors=True)


def read_ready_deps(module_dir: Path, dependencies: Sequence[str]) -> Path | None:
    """冻结模式：返回已安装依赖目录；标记缺失/hash 不符时为 None。"""
    normalized = validate_dependencies(dependencies)
    if not normalized:
        return None
    directory = module_deps_dir(module_dir)
    marker = directory / _DEPS_MARKER
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("dependencyHash") != dependency_digest(normalized):
        return None
    return directory if directory.is_dir() else None


def read_ready_venv(module_dir: Path, dependencies: Sequence[str]) -> Path | None:
    """返回可用的 venv Python；依赖为空、标记缺失、hash 不符或解释器缺失时为 None。"""
    normalized = validate_dependencies(dependencies)
    if not normalized:
        return None
    marker = module_venv_dir(module_dir) / _READY_MARKER
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("dependencyHash") != dependency_digest(normalized):
        return None
    python = venv_python_path(module_venv_dir(module_dir))
    return python if python.is_file() else None


def _install_error(reason: str, message: str) -> ModuleError:
    # errors.py 不在本批所有权内，无法新增顶层码；用 detail 明确标记安装失败原因。
    return ModuleError(
        "MODULE_ERROR",
        message,
        {"installError": "MODULE_INSTALL_FAILED", "reason": reason},
    )


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _dependency_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _run_command(args: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env=_dependency_env(),
        creationflags=_creation_flags(),
    )


def _log_output(log: Callable[[str], None] | None, result: subprocess.CompletedProcess[str]) -> None:
    """只记录截断后的输出摘要，避免把完整 pip 日志塞进模块日志。"""
    if log is None:
        return
    tail = ((result.stdout or "") + (result.stderr or "")).strip()
    if tail:
        log(f"[deps] rc={result.returncode} {tail[-_MAX_LOG_CHARS:]}")


def _write_module_path(venv_dir: Path, module_dir: Path) -> None:
    """把模块目录写入 venv 的 .pth：等价于 PYTHONPATH，但不改核心进程环境。

    用相对路径，避免中文/空格路径在 .pth 解码时出问题。
    """
    site = _site_packages_dir(venv_dir)
    site.mkdir(parents=True, exist_ok=True)
    relative = os.path.relpath(module_dir, site)
    (site / _PATH_FILE).write_text(relative + "\n", encoding="utf-8")


def _write_ready_marker(venv_dir: Path, dependencies: Sequence[str]) -> None:
    marker = venv_dir / _READY_MARKER
    payload = {
        "dependencyHash": dependency_digest(dependencies),
        "dependencies": list(dependencies),
        "installedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "python": sys.version.split()[0],
    }
    temp = marker.parent / (marker.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(marker)


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def _install_deps_frozen(
    module_dir: Path,
    dependencies: Sequence[str],
    *,
    timeout_s: float,
    log: Callable[[str], None] | None,
) -> Path:
    """冻结版没有 python.exe：用随包 pip 安装到 deps/，worker 通过 sys.path 使用。"""
    deps_dir = module_deps_dir(module_dir)
    shutil.rmtree(deps_dir, ignore_errors=True)
    deps_dir.mkdir(parents=True, exist_ok=True)
    helper = _bundle_root() / "pip_install.py"
    if not helper.is_file():
        raise _install_error("pip-helper-missing", "安装包缺少 pip 安装器")
    if log is not None:
        log(f"[deps] frozen install into deps/ for {len(dependencies)} requirement(s)")
    result = _run_command(
        [
            sys.executable,
            str(helper),
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-warn-script-location",
            "--target",
            str(deps_dir),
            *dependencies,
        ],
        timeout_s,
    )
    _log_output(log, result)
    if result.returncode != 0:
        shutil.rmtree(deps_dir, ignore_errors=True)
        raise _install_error(
            "pip-install-failed",
            "依赖安装失败（网络、版本冲突或包不可用）",
        )
    payload = {
        "dependencyHash": dependency_digest(dependencies),
        "dependencies": list(dependencies),
        "installedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "python": sys.version.split()[0],
    }
    (deps_dir / _DEPS_MARKER).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if log is not None:
        log(f"[deps] frozen ready: {len(dependencies)} requirement(s)")
    return deps_dir


def install_module_venv(
    module_dir: Path,
    dependencies: Sequence[str],
    *,
    timeout_s: float = DEPENDENCY_INSTALL_TIMEOUT_S,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """在模块版本目录内创建 venv 并安装锁定依赖。

    依赖为空不建 venv；任一步失败都会删除半成品，保证不会留下「已安装但跑不起来」。
    返回 venv 目录，无依赖时返回 None。
    """
    normalized = validate_dependencies(dependencies)
    remove_module_venv(module_dir)
    if not normalized:
        return None

    if getattr(sys, "frozen", False):
        try:
            return _install_deps_frozen(
                module_dir, normalized, timeout_s=timeout_s, log=log
            )
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(module_deps_dir(module_dir), ignore_errors=True)
            raise _install_error("timeout", f"依赖安装超过 {int(timeout_s)} 秒，已回滚") from exc

    venv_dir = module_venv_dir(module_dir)
    try:
        if log is not None:
            log(f"[deps] creating venv for {len(normalized)} requirement(s)")
        created = _run_command([sys.executable, "-m", "venv", str(venv_dir)], timeout_s)
        _log_output(log, created)
        if created.returncode != 0:
            raise _install_error("venv-create-failed", "无法创建模块虚拟环境")

        python = venv_python_path(venv_dir)
        if not python.is_file():
            raise _install_error("python-venv-missing", "虚拟环境缺少 Python 解释器")
        installed = _run_command(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-warn-script-location",
                *normalized,
            ],
            timeout_s,
        )
        _log_output(log, installed)
        if installed.returncode != 0:
            stderr = installed.stderr or ""
            if "No module named pip" in stderr:
                raise _install_error("pip-missing", "模块虚拟环境缺少 pip，无法安装依赖")
            raise _install_error("pip-install-failed", "依赖安装失败（网络、版本冲突或包不可用）")

        _write_module_path(venv_dir, module_dir)
        _write_ready_marker(venv_dir, normalized)
        if log is not None:
            log(f"[deps] ready: {len(normalized)} requirement(s)")
        return venv_dir
    except subprocess.TimeoutExpired as exc:
        remove_module_venv(module_dir)
        raise _install_error("timeout", f"依赖安装超过 {int(timeout_s)} 秒，已回滚") from exc
    except ModuleError:
        remove_module_venv(module_dir)
        raise
    except OSError as exc:
        remove_module_venv(module_dir)
        reason = "disk-full" if getattr(exc, "errno", None) == errno.ENOSPC else "io-error"
        raise _install_error(reason, "依赖安装时无法启动进程或写入磁盘") from exc

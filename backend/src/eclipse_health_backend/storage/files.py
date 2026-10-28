"""文件存储：波形 float32 小端、报告文件。

规则（Schema §11 / §15）：
- 文件名由服务端生成，绝不拼接用户输入；
- 写入先落临时文件再 ``os.replace``，避免半截文件；
- 写时算 sha256 并入库，读时校验；
- 不保存原始文件名，只存哈希。
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from ..domain.errors import InvalidInputError, StorageIntegrityError
from ..settings import get_settings

SIGNAL_RELATIVE_RE = re.compile(r"^signals/[A-Za-z0-9_.-]{1,120}\.f32$")
REPORT_RELATIVE_RE = re.compile(r"^reports/[A-Za-z0-9_.-]{1,120}\.(?:pdf|png)$")
SIGNAL_ID_RE = re.compile(r"^sig_[0-9a-f-]{36}$")
REPORT_ID_RE = re.compile(r"^rep_[0-9a-f-]{36}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def encode_float32(values: Sequence[float] | np.ndarray) -> bytes:
    array = np.asarray(values, dtype="<f4")
    if array.ndim != 1:
        array = array.reshape(-1)
    return array.tobytes(order="C")


def decode_float32(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<f4")


def _safe_join(root: Path, relative: str, pattern: re.Pattern[str]) -> Path:
    if "\\" in relative or not pattern.match(relative):
        raise StorageIntegrityError(
            "invalid stored file reference", details={"path": relative}
        )
    target = (root / relative).resolve()
    root_resolved = root.resolve()
    if not target.is_relative_to(root_resolved):
        raise StorageIntegrityError("path escapes data directory", details={"path": relative})
    return target


def signal_relative_path(signal_id: str) -> str:
    if not SIGNAL_ID_RE.match(signal_id):
        raise ValueError(f"invalid signal id: {signal_id}")
    return f"signals/{signal_id}.f32"


def write_signal(signal_id: str, samples: Sequence[float] | np.ndarray) -> tuple[str, str, int]:
    """写入一个导联的 float32；返回 (relativePath, sha256, byteSize)。"""
    settings = get_settings()
    payload = encode_float32(samples)
    if len(payload) > settings.signal_max_bytes:
        raise InvalidInputError(
            "signal file too large",
            code="signal_too_large",
            details={"bytes": len(payload), "limit": settings.signal_max_bytes},
        )
    relative = signal_relative_path(signal_id)
    path = settings.signals_dir / f"{signal_id}.f32"
    atomic_write_bytes(path, payload)
    return relative, sha256_hex(payload), len(payload)


def read_signal(relative_path: str, expected_sha256: str) -> bytes:
    settings = get_settings()
    path = _safe_join(settings.data_dir, relative_path, SIGNAL_RELATIVE_RE)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise StorageIntegrityError(
            "signal file missing", details={"path": relative_path}
        ) from exc
    actual = sha256_hex(data)
    if actual != expected_sha256:
        raise StorageIntegrityError(
            "signal file checksum mismatch",
            details={"path": relative_path, "expected": expected_sha256, "actual": actual},
        )
    return data


def delete_signal(relative_path: str) -> None:
    settings = get_settings()
    try:
        path = _safe_join(settings.data_dir, relative_path, SIGNAL_RELATIVE_RE)
    except StorageIntegrityError:
        return
    path.unlink(missing_ok=True)


def write_report(report_id: str, extension: str, data: bytes) -> tuple[str, str, int]:
    settings = get_settings()
    extension = extension.lower().lstrip(".")
    if extension not in {"pdf", "png"}:
        raise InvalidInputError(
            "unsupported report format", code="unsupported_format", details={"extension": extension}
        )
    if not REPORT_ID_RE.match(report_id):
        raise ValueError(f"invalid report id: {report_id}")
    relative = f"reports/{report_id}.{extension}"
    path = settings.reports_dir / f"{report_id}.{extension}"
    atomic_write_bytes(path, data)
    return relative, sha256_hex(data), len(data)


def read_report(relative_path: str, expected_sha256: str) -> bytes:
    settings = get_settings()
    path = _safe_join(settings.data_dir, relative_path, REPORT_RELATIVE_RE)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise StorageIntegrityError(
            "report file missing", details={"path": relative_path}
        ) from exc
    actual = sha256_hex(data)
    if actual != expected_sha256:
        raise StorageIntegrityError(
            "report file checksum mismatch",
            details={"path": relative_path, "expected": expected_sha256, "actual": actual},
        )
    return data


def read_import_file(file_ref: str) -> bytes:
    """读取用户提供的导入文件。

    ``file_ref`` 只接受 ``imports/`` 下的相对路径；绝对路径、``..``、符号链接逃逸一律拒绝。
    """
    settings = get_settings()
    settings.ensure_dirs()
    if not file_ref or Path(file_ref).is_absolute() or re.match(r"^[A-Za-z]:", file_ref):
        raise InvalidInputError(
            "fileRef must be a relative path under the imports directory",
            code="invalid_file_ref",
            details={"fileRef": file_ref},
        )
    normalized = file_ref.replace("\\", "/")
    if "\\" in file_ref or ".." in normalized.split("/"):
        raise InvalidInputError(
            "fileRef must not contain traversal segments",
            code="invalid_file_ref",
            details={"fileRef": file_ref},
        )
    root = settings.imports_dir.resolve()
    target = (root / normalized).resolve()
    if not target.is_relative_to(root):
        raise InvalidInputError(
            "fileRef escapes the imports directory",
            code="invalid_file_ref",
            details={"fileRef": file_ref},
        )
    if not target.is_file():
        raise InvalidInputError(
            "fileRef not found",
            code="invalid_file_ref",
            details={"fileRef": file_ref},
        )
    size = target.stat().st_size
    if size > settings.signal_max_bytes:
        raise InvalidInputError(
            "signal file too large",
            code="signal_too_large",
            details={"bytes": size, "limit": settings.signal_max_bytes},
        )
    return target.read_bytes()


__all__ = [
    "atomic_write_bytes",
    "decode_float32",
    "delete_signal",
    "encode_float32",
    "read_import_file",
    "read_report",
    "read_signal",
    "sha256_hex",
    "signal_relative_path",
    "write_report",
    "write_signal",
]

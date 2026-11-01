"""导入工作区：``<data>/imports/<importId>/``。

生命周期：预览时创建 → commit / delete / 24h TTL 清理。
上传文件保存在工作区内；``path`` 调试参数只记指针，绝不动用户的原始文件。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from starlette.datastructures import UploadFile

from ..domain.ids import uuid7
from ..settings import get_settings
from ..storage.files import atomic_write_bytes, sha256_hex
from . import limits
from .errors import ImportConflictError, ImportNotFoundError, ImportTooLargeError, invalid_file

IMPORT_ID_RE = re.compile(
    r"^imp_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
META_FILE = "meta.json"
UPLOAD_DIR = "input"
EXTRACTED_DIR = "extracted"


def new_import_id() -> str:
    return f"imp_{uuid7()}"


def is_valid_import_id(import_id: str) -> bool:
    return bool(IMPORT_ID_RE.match(import_id or ""))


def _imports_root() -> Path:
    root = get_settings().imports_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_workspace(import_id: str) -> Path:
    workspace = _imports_root() / import_id
    try:
        workspace.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ImportConflictError("import workspace already exists") from exc
    return workspace


def workspace_path(import_id: str) -> Path:
    if not is_valid_import_id(import_id):
        raise ImportNotFoundError(
            "import not found", code="import_not_found", details={"id": import_id}
        )
    path = _imports_root() / import_id
    if path.is_symlink() or not path.is_dir():
        raise ImportNotFoundError(
            "import not found", code="import_not_found", details={"id": import_id}
        )
    return path


def workspace_file(workspace: Path, relative: str) -> Path:
    """把 meta 里的相对路径限制在工作区内，防止伪造 meta 越界读取。"""
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
        raise invalid_file("工作区路径非法", details={"path": relative})
    target = (workspace / Path(*candidate.parts)).resolve()
    if not target.is_relative_to(workspace.resolve()):
        raise invalid_file("工作区路径越界", details={"path": relative})
    return target


def _remove(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


def delete_workspace_path(workspace: Path) -> None:
    _remove(Path(workspace))


def delete_workspace(import_id: str) -> None:
    if not is_valid_import_id(import_id):
        return
    _remove(_imports_root() / import_id)


def filename_hash(name: str | None) -> str:
    return f"sha256:{sha256_hex(str(name or '').encode('utf-8'))}"


def save_upload(workspace: Path, upload: UploadFile) -> tuple[Path, str, str]:
    """流式落盘并计算哈希；超过上限立即中止并删除半截文件。"""
    original = Path(upload.filename or "upload.bin").name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", original)[:100] or "upload.bin"
    if safe in {".", ".."}:
        safe = "upload.bin"
    target_dir = workspace / UPLOAD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe

    digest = hashlib.sha256()
    total = 0
    upload.file.seek(0)
    try:
        with target.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.MAX_UPLOAD_BYTES:
                    raise ImportTooLargeError(
                        "上传文件超过大小上限",
                        details={"limit": limits.MAX_UPLOAD_BYTES, "bytes": total},
                    )
                digest.update(chunk)
                handle.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if total == 0:
        target.unlink(missing_ok=True)
        raise invalid_file("上传文件为空")
    return target, f"sha256:{digest.hexdigest()}", filename_hash(original)


def is_zip(path: Path) -> bool:
    if path.suffix.lower() == ".zip":
        return True
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def zip_is_encrypted(path: Path) -> bool:
    """加密 ZIP 无法解压；交给适配器给出 ``encrypted_export`` 之类的明确错误。"""
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            return any(info.flag_bits & 0x1 for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        return False


def _entry_name(info: Any) -> PurePosixPath:
    raw = info.filename or ""
    if not raw or "\\" in raw:
        raise invalid_file("ZIP 条目名非法", code="zip_unsafe", details={"entry": raw})
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in raw:
        raise invalid_file(
            "ZIP 包含路径穿越条目", code="zip_traversal", details={"entry": raw}
        )
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise invalid_file("ZIP 包含符号链接", code="zip_unsafe", details={"entry": raw})
    if info.flag_bits & 0x1:
        raise invalid_file("ZIP 已加密，无法导入", code="zip_unsafe", details={"entry": raw})
    return candidate


def extract_zip(zip_path: Path, workspace: Path) -> Path:
    """安全解压到工作区：拒绝穿越/符号链接，限制文件数与解压总量。"""
    import zipfile

    destination = workspace / EXTRACTED_DIR
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > limits.ZIP_MAX_FILES:
                raise invalid_file(
                    "ZIP 文件数超过上限",
                    code="archive_too_large",
                    details={"files": len(infos), "limit": limits.ZIP_MAX_FILES},
                )
            declared = sum(info.file_size for info in infos)
            if declared > limits.ZIP_MAX_TOTAL_BYTES:
                raise invalid_file(
                    "ZIP 解压后超过大小上限",
                    code="archive_too_large",
                    details={"bytes": declared, "limit": limits.ZIP_MAX_TOTAL_BYTES},
                )

            root = destination.resolve()
            written = 0
            for info in infos:
                relative = _entry_name(info)
                target = root.joinpath(*relative.parts)
                resolved = target.resolve()
                if not resolved.is_relative_to(root):
                    raise invalid_file(
                        "ZIP 条目越界", code="zip_traversal", details={"entry": info.filename}
                    )
                resolved.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, resolved.open("wb") as sink:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > limits.ZIP_MAX_TOTAL_BYTES:
                            raise invalid_file(
                                "ZIP 解压后超过大小上限",
                                code="archive_too_large",
                                details={"limit": limits.ZIP_MAX_TOTAL_BYTES},
                            )
                        sink.write(chunk)
    except zipfile.BadZipFile as exc:
        _remove(destination)
        raise invalid_file("压缩包损坏", details={"reason": str(exc)}) from exc
    except BaseException:
        _remove(destination)
        raise
    return destination


def hash_bytes_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def hash_path_source(path: Path) -> str:
    """目录/文件夹路径（调试）只做内容指纹，不影响正式上传路径。"""
    if path.is_dir():
        digest = hashlib.sha256()
        files = sorted(p for p in path.iterdir() if p.is_file() and not p.is_symlink())
        for item in files:
            digest.update(item.name.encode("utf-8"))
            digest.update(item.read_bytes())
        return f"sha256:{digest.hexdigest()}"
    if path.suffix.lower() == ".hea":
        digest = hashlib.sha256()
        for sibling in sorted(path.parent.glob(f"{path.stem}.*")):
            if sibling.is_file():
                digest.update(sibling.name.encode("utf-8"))
                digest.update(sibling.read_bytes())
        return f"sha256:{digest.hexdigest()}"
    return hash_bytes_file(path)


def write_meta(workspace: Path, meta: dict[str, Any]) -> None:
    payload = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(workspace / META_FILE, payload)


def read_meta(workspace: Path) -> dict[str, Any]:
    try:
        raw = (workspace / META_FILE).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ImportNotFoundError(
            "import workspace is missing or corrupted",
            code="import_not_found",
            details={"missing": META_FILE},
        ) from exc
    if not isinstance(data, dict) or not is_valid_import_id(str(data.get("importId", ""))):
        raise ImportNotFoundError(
            "import workspace is missing or corrupted", code="import_not_found"
        )
    return data


def _created_at(meta: dict[str, Any], fallback: Path) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(meta.get("createdAt", "")))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(fallback.stat().st_mtime, tz=UTC)


def load_workspace(import_id: str) -> tuple[Path, dict[str, Any]]:
    workspace = workspace_path(import_id)
    meta = read_meta(workspace)
    ttl = timedelta(hours=limits.IMPORT_TTL_HOURS)
    if datetime.now(UTC) - _created_at(meta, workspace) > ttl:
        _remove(workspace)
        raise ImportNotFoundError(
            "import expired",
            code="import_expired",
            details={"id": import_id, "ttlHours": limits.IMPORT_TTL_HOURS},
        )
    return workspace, meta


def cleanup_expired(
    *, now: datetime | None = None, ttl: timedelta | None = None
) -> list[str]:
    """删除超过 TTL 的工作区；preview 入口调用，测试可直接注入时间。"""
    moment = now or datetime.now(UTC)
    window = ttl if ttl is not None else timedelta(hours=limits.IMPORT_TTL_HOURS)
    removed: list[str] = []
    for entry in _imports_root().iterdir():
        if not entry.is_dir() or entry.is_symlink() or not is_valid_import_id(entry.name):
            continue
        try:
            meta = read_meta(entry)
            created = _created_at(meta, entry)
        except ImportNotFoundError:
            created = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        if moment - created > window:
            _remove(entry)
            removed.append(entry.name)
    return removed


__all__ = [
    "IMPORT_ID_RE",
    "META_FILE",
    "cleanup_expired",
    "create_workspace",
    "delete_workspace",
    "delete_workspace_path",
    "extract_zip",
    "filename_hash",
    "hash_path_source",
    "is_valid_import_id",
    "is_zip",
    "load_workspace",
    "new_import_id",
    "read_meta",
    "save_upload",
    "workspace_file",
    "workspace_path",
    "write_meta",
    "zip_is_encrypted",
]

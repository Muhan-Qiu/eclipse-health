"""Agent 导入 session 工作区：``<data>/import-agent/<sessionId>/``。

目录：

```
ias_<uuid7>/
  meta.json         会话状态、文件清单、提交结果（提交后保留到 TTL）
  input/            本次上传文件的副本（Agent 唯一可读的原始数据）
  work/             脚本与运行目录（run_python 的 cwd）
  output/           Agent 写出的中间结果 / ECG 采样文件 / proposals.json
```

所有工具路径都经过 ``safe_join``，拒绝绝对路径、``..``、反斜杠、盘符与符号链接逃逸。
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
from ..storage.files import atomic_write_bytes
from . import limits
from .errors import ImportAgentError, session_expired, session_not_found

SESSION_ID_RE = re.compile(r"^ias_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
META_FILE = "meta.json"
INPUT_DIR = "input"
WORK_DIR = "work"
OUTPUT_DIR = "output"
PROPOSALS_FILE = "proposals.json"

TEXT_KINDS = {"text", "csv", "json", "xml", "html"}
_KIND_BY_SUFFIX = {
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
    ".md": "text",
    ".log": "text",
    ".pdf": "pdf",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xlsx",
    ".zip": "zip",
    ".fit": "binary",
    ".gpx": "xml",
    ".tcx": "xml",
    ".edf": "binary",
    ".dat": "binary",
    ".f32": "binary",
    ".png": "binary",
    ".jpg": "binary",
    ".jpeg": "binary",
}

_UNSAFE_NAME = re.compile(r"[^\w.\- ()\[\]一-鿿]", re.UNICODE)
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #


def _root() -> Path:
    root = get_settings().import_agent_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_session_id() -> str:
    return f"ias_{uuid7()}"


def is_valid_session_id(session_id: str) -> bool:
    return bool(SESSION_ID_RE.match(session_id or ""))


def session_path(session_id: str) -> Path:
    if not is_valid_session_id(session_id):
        raise session_not_found(session_id)
    path = _root() / session_id
    if path.is_symlink() or not path.is_dir():
        raise session_not_found(session_id)
    return path


def create_workspace(session_id: str) -> Path:
    workspace = _root() / session_id
    try:
        workspace.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ImportAgentError("session already exists", code="conflict", status_code=409) from exc
    for name in (INPUT_DIR, WORK_DIR, OUTPUT_DIR):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return workspace


def safe_join(root: Path, relative: str) -> Path:
    """把相对路径限制在 root 内；拒绝穿越、盘符、反斜杠与符号链接。"""
    raw = str(relative or "")
    if not raw or "\x00" in raw:
        raise ImportAgentError("path is empty", code="path_escape")
    if "\\" in raw or ":" in raw:
        raise ImportAgentError("path must be a relative POSIX path", code="path_escape")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ImportAgentError("path escapes the session directory", code="path_escape")
    target = (root / Path(*candidate.parts)).resolve()
    resolved_root = root.resolve()
    if not target.is_relative_to(resolved_root):
        raise ImportAgentError("path escapes the session directory", code="path_escape")
    if target.exists() and target.is_symlink():
        raise ImportAgentError("symlinks are not allowed", code="path_escape")
    return target


def input_path(session_id: str, relative: str) -> Path:
    return safe_join(session_path(session_id) / INPUT_DIR, relative)


def work_path(session_id: str, relative: str) -> Path:
    return safe_join(session_path(session_id) / WORK_DIR, relative)


def output_path(session_id: str, relative: str) -> Path:
    return safe_join(session_path(session_id) / OUTPUT_DIR, relative)


# --------------------------------------------------------------------------- #
# meta
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(UTC)


def _created_at(meta: dict[str, Any], fallback: Path) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(meta.get("createdAt", "")))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(fallback.stat().st_mtime, tz=UTC)


def write_meta(workspace: Path, meta: dict[str, Any]) -> None:
    payload = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(workspace / META_FILE, payload)


def read_meta(workspace: Path) -> dict[str, Any]:
    try:
        data = json.loads((workspace / META_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImportAgentError(
            "session metadata is missing or corrupted",
            code="session_corrupted",
            status_code=500,
        ) from exc
    if not isinstance(data, dict) or not is_valid_session_id(str(data.get("sessionId", ""))):
        raise ImportAgentError(
            "session metadata is corrupted", code="session_corrupted", status_code=500
        )
    return data


def load_session(session_id: str) -> tuple[Path, dict[str, Any]]:
    workspace = session_path(session_id)
    meta = read_meta(workspace)
    ttl = timedelta(hours=limits.SESSION_TTL_HOURS)
    if _now() - _created_at(meta, workspace) > ttl:
        _remove(workspace)
        raise session_expired(session_id)
    return workspace, meta


def _remove(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


def delete_session(session_id: str) -> bool:
    if not is_valid_session_id(session_id):
        return False
    workspace = _root() / session_id
    existed = workspace.is_dir()
    _remove(workspace)
    return existed


def delete_payload_dirs(workspace: Path) -> None:
    """提交/放弃后删除原始文件与中间产物，只保留 meta.json。"""
    for name in (INPUT_DIR, WORK_DIR, OUTPUT_DIR):
        _remove(workspace / name)


def cleanup_expired(
    *, now: datetime | None = None, ttl: timedelta | None = None
) -> list[str]:
    moment = now or _now()
    window = ttl if ttl is not None else timedelta(hours=limits.SESSION_TTL_HOURS)
    removed: list[str] = []
    for entry in _root().iterdir():
        if not entry.is_dir() or entry.is_symlink() or not is_valid_session_id(entry.name):
            continue
        try:
            meta = read_meta(entry)
            created = _created_at(meta, entry)
        except ImportAgentError:
            created = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        if moment - created > window:
            _remove(entry)
            removed.append(entry.name)
    return removed


def list_sessions(limit: int = limits.MAX_SESSION_LIST) -> list[dict[str, Any]]:
    cleanup_expired()
    items: list[dict[str, Any]] = []
    for entry in _root().iterdir():
        if not entry.is_dir() or entry.is_symlink() or not is_valid_session_id(entry.name):
            continue
        try:
            meta = read_meta(entry)
        except ImportAgentError:
            continue
        items.append(meta)
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return items[: max(1, min(limit, limits.MAX_SESSION_LIST))]


# --------------------------------------------------------------------------- #
# 上传
# --------------------------------------------------------------------------- #


def _safe_name(raw: str | None, *, fallback: str = "upload.bin") -> str:
    original = Path(str(raw or fallback).replace("\\", "/")).name or fallback
    cleaned = _UNSAFE_NAME.sub("_", original).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = fallback
    stem, suffix = Path(cleaned).stem, Path(cleaned).suffix
    if stem.lower() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    cleaned = f"{stem}{suffix}"[:120]
    return cleaned or fallback


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 2
    while f"{stem} ({index}){suffix}" in used:
        index += 1
    chosen = f"{stem} ({index}){suffix}"
    used.add(chosen)
    return chosen


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _file_kind(name: str, path: Path) -> str:
    suffix = Path(name).suffix.lower()
    kind = _KIND_BY_SUFFIX.get(suffix)
    if kind:
        return kind
    try:
        with path.open("rb") as handle:
            head = handle.read(4096)
    except OSError:
        return "binary"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if b"\x00" in head:
        return "binary"
    stripped = head.lstrip()
    if stripped.startswith((b"<", b"{")):
        return "xml" if stripped.startswith(b"<") else "json"
    return "text"


def _entry(name: str, stored: Path) -> dict[str, Any]:
    return {
        "name": name,
        "storedName": stored.name,
        "size": stored.stat().st_size,
        "sha256": _hash_file(stored),
        "kind": _file_kind(name, stored),
    }


def stage_uploads(
    workspace: Path,
    uploads: list[UploadFile],
    raw_path: str | None,
) -> list[dict[str, Any]]:
    """把上传文件/目录复制到 input/；返回文件清单。"""
    if uploads and raw_path:
        raise ImportAgentError("file(s) and path are mutually exclusive", code="invalid_file")
    if not uploads and not raw_path:
        raise ImportAgentError(
            "provide at least one uploaded file or a local path", code="invalid_file"
        )
    target_dir = workspace / INPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    entries: list[dict[str, Any]] = []
    total = 0

    if uploads:
        if len(uploads) > limits.MAX_FILES:
            raise ImportAgentError(
                f"at most {limits.MAX_FILES} files per session",
                code="too_many_files",
                details={"count": len(uploads), "limit": limits.MAX_FILES},
            )
        for upload in uploads:
            name = _unique_name(_safe_name(upload.filename), used)
            target = target_dir / name
            digest = hashlib.sha256()
            size = 0
            upload.file.seek(0)
            try:
                with target.open("wb") as handle:
                    while chunk := upload.file.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > limits.MAX_FILE_BYTES:
                            raise ImportAgentError(
                                "file exceeds the size limit",
                                code="file_too_large",
                                status_code=413,
                                details={"name": name, "limit": limits.MAX_FILE_BYTES},
                            )
                        if total > limits.MAX_TOTAL_BYTES:
                            raise ImportAgentError(
                                "session exceeds the total size limit",
                                code="file_too_large",
                                status_code=413,
                                details={"limit": limits.MAX_TOTAL_BYTES},
                            )
                        digest.update(chunk)
                        handle.write(chunk)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            if size == 0:
                target.unlink(missing_ok=True)
                raise ImportAgentError("uploaded file is empty", code="invalid_file")
            entries.append(
                {
                    "name": name,
                    "storedName": name,
                    "size": size,
                    "sha256": f"sha256:{digest.hexdigest()}",
                    "kind": _file_kind(name, target),
                }
            )
        return entries

    source = _validate_local_path(raw_path or "")
    if source.is_dir():
        return _stage_directory(source, target_dir)
    name = _safe_name(source.name)
    target = target_dir / name
    shutil.copyfile(source, target)
    size = target.stat().st_size
    if size > limits.MAX_FILE_BYTES:
        target.unlink(missing_ok=True)
        raise ImportAgentError(
            "file exceeds the size limit",
            code="file_too_large",
            status_code=413,
            details={"name": name, "limit": limits.MAX_FILE_BYTES},
        )
    return [_entry(name, target)]


def _validate_local_path(raw: str) -> Path:
    candidate = Path(str(raw).strip().strip('"'))
    if not candidate.is_absolute():
        raise ImportAgentError("path must be absolute (debug only)", code="invalid_file")
    if ".." in candidate.parts:
        raise ImportAgentError("path must not contain ..", code="invalid_file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ImportAgentError("path does not exist", code="invalid_file") from exc
    if resolved.is_symlink():
        raise ImportAgentError("path must not be a symlink", code="invalid_file")
    if not resolved.is_file() and not resolved.is_dir():
        raise ImportAgentError("path is not a regular file or directory", code="invalid_file")
    return resolved


def _stage_directory(source: Path, target_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    total = 0
    for path in sorted(source.rglob("*")):
        if len(entries) >= limits.MAX_DIR_FILES:
            raise ImportAgentError(
                f"directory contains more than {limits.MAX_DIR_FILES} files",
                code="too_many_files",
                details={"limit": limits.MAX_DIR_FILES},
            )
        if path.is_symlink():
            raise ImportAgentError("directory contains a symlink", code="invalid_file")
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        parts = [_safe_name(part, fallback="_") for part in relative.split("/")]
        name = "/".join(parts)
        target = safe_join(target_dir, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        size = target.stat().st_size
        total += size
        if total > limits.MAX_TOTAL_BYTES:
            raise ImportAgentError(
                "directory exceeds the total size limit",
                code="file_too_large",
                status_code=413,
                details={"limit": limits.MAX_TOTAL_BYTES},
            )
        entries.append(_entry(name, target))
    if not entries:
        raise ImportAgentError("directory contains no files", code="invalid_file")
    return entries


# --------------------------------------------------------------------------- #
# 文本读取
# --------------------------------------------------------------------------- #


def detect_encoding(path: Path) -> str:
    with path.open("rb") as handle:
        sample = handle.read(64 * 1024)
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        sample.decode("gb18030")
        return "gb18030"
    except UnicodeDecodeError:
        return "latin-1"


def _is_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        sample = handle.read(4096)
    return b"\x00" in sample and not sample.startswith((b"\xff\xfe", b"\xfe\xff"))


def read_text_slice(
    session_id: str, relative: str, *, offset: int = 0, limit: int = limits.MAX_READ_TEXT_BYTES
) -> dict[str, Any]:
    target = input_path(session_id, relative)
    if not target.is_file():
        raise ImportAgentError("input file not found", code="not_found", details={"path": relative})
    size = target.stat().st_size
    if _is_binary(target):
        raise ImportAgentError(
            "binary file cannot be read as text; use run_python with helpers",
            code="binary_file",
            details={"path": relative},
        )
    offset = max(0, min(int(offset), size))
    limit = max(1, min(int(limit), limits.MAX_READ_TEXT_BYTES))
    encoding = detect_encoding(target)
    with target.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(limit)
    text = data.decode(encoding, errors="replace")
    end = offset + len(data)
    return {
        "path": relative,
        "offset": offset,
        "bytesRead": len(data),
        "size": size,
        "encoding": encoding,
        "text": text,
        "truncated": end < size,
        "nextOffset": end,
    }


def read_output_slice(
    session_id: str, relative: str, *, offset: int = 0, limit: int = limits.MAX_READ_TEXT_BYTES
) -> dict[str, Any]:
    target = output_path(session_id, relative)
    if not target.is_file():
        raise ImportAgentError("output file not found", code="not_found", details={"path": relative})
    size = target.stat().st_size
    offset = max(0, min(int(offset), size))
    limit = max(1, min(int(limit), limits.MAX_READ_TEXT_BYTES))
    encoding = detect_encoding(target)
    with target.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(limit)
    end = offset + len(data)
    return {
        "path": relative,
        "offset": offset,
        "bytesRead": len(data),
        "size": size,
        "encoding": encoding,
        "text": data.decode(encoding, errors="replace"),
        "truncated": end < size,
        "nextOffset": end,
    }


def write_output_text(session_id: str, relative: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ImportAgentError("content must be a string", code="invalid_argument")
    data = content.encode("utf-8")
    if len(data) > limits.MAX_WRITE_OUTPUT_BYTES:
        raise ImportAgentError(
            "output exceeds the size limit",
            code="file_too_large",
            details={"bytes": len(data), "limit": limits.MAX_WRITE_OUTPUT_BYTES},
        )
    target = output_path(session_id, relative)
    atomic_write_bytes(target, data)
    return {
        "path": relative,
        "bytes": len(data),
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
    }


def write_script(session_id: str, name: str, code: str) -> dict[str, Any]:
    if not isinstance(code, str) or not code.strip():
        raise ImportAgentError("script code must not be empty", code="invalid_argument")
    data = code.encode("utf-8")
    if len(data) > limits.MAX_SCRIPT_BYTES:
        raise ImportAgentError(
            "script exceeds the size limit",
            code="file_too_large",
            details={"bytes": len(data), "limit": limits.MAX_SCRIPT_BYTES},
        )
    safe = _safe_name(name, fallback="script.py")
    if not safe.lower().endswith(".py"):
        safe = f"{safe}.py"
    if safe.startswith("_eh_"):
        raise ImportAgentError("script name is reserved", code="invalid_argument")
    relative = f"scripts/{safe}"
    target = work_path(session_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, data)
    return {"path": relative, "bytes": len(data)}


# --------------------------------------------------------------------------- #
# 候选
# --------------------------------------------------------------------------- #


def proposals_file(workspace: Path) -> Path:
    return workspace / OUTPUT_DIR / PROPOSALS_FILE


def load_proposals(workspace: Path) -> list[dict[str, Any]]:
    path = proposals_file(workspace)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def save_proposals(workspace: Path, proposals: list[dict[str, Any]]) -> None:
    path = proposals_file(workspace)
    payload = json.dumps({"items": proposals}, ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(path, payload)


def reset_work_dirs(workspace: Path) -> None:
    for name in (WORK_DIR, OUTPUT_DIR):
        _remove(workspace / name)
        (workspace / name).mkdir(parents=True, exist_ok=True)


def file_names(meta: dict[str, Any]) -> set[str]:
    return {
        str(item.get("storedName") or item.get("name"))
        for item in meta.get("files") or []
        if isinstance(item, dict)
    }


def file_hash_for(meta: dict[str, Any], evidence_file: str) -> str:
    """按 evidence 的顶层文件名找上传文件哈希；找不到返回空串。"""
    top = str(evidence_file or "").replace("\\", "/").split("/", 1)[0]
    for item in meta.get("files") or []:
        if not isinstance(item, dict):
            continue
        if top in {item.get("name"), item.get("storedName")}:
            return str(item.get("sha256") or "")
    return ""


def session_view(meta: dict[str, Any], *, include_files: bool = True) -> dict[str, Any]:
    view = {
        "sessionId": meta.get("sessionId"),
        "status": meta.get("status", "created"),
        "createdAt": meta.get("createdAt"),
        "expiresAt": meta.get("expiresAt"),
        "providerId": meta.get("providerId"),
        "files": list(meta.get("files") or []) if include_files else [],
        "fileCount": len(meta.get("files") or []),
        "limits": {
            "maxFiles": limits.MAX_FILES,
            "maxUploadBytes": limits.MAX_FILE_BYTES,
            "maxToolCalls": limits.MAX_TOOL_CALLS,
            "maxTurnSeconds": int(limits.MAX_TURN_SECONDS),
            "maxRunSeconds": int(limits.DEFAULT_RUN_TIMEOUT_SECONDS),
            "maxProposalRecords": limits.MAX_PROPOSALS,
            "network": False,
        },
        "proposalCount": int(meta.get("proposalCount") or 0),
        "summary": meta.get("summary"),
        "toolCalls": int(meta.get("toolCalls") or 0),
        "lastError": meta.get("lastError"),
        "commit": meta.get("commit"),
    }
    return view


__all__ = [
    "INPUT_DIR",
    "META_FILE",
    "OUTPUT_DIR",
    "PROPOSALS_FILE",
    "WORK_DIR",
    "cleanup_expired",
    "create_workspace",
    "delete_payload_dirs",
    "delete_session",
    "detect_encoding",
    "file_hash_for",
    "file_names",
    "input_path",
    "is_valid_session_id",
    "list_sessions",
    "load_proposals",
    "load_session",
    "new_session_id",
    "output_path",
    "proposals_file",
    "read_meta",
    "read_output_slice",
    "read_text_slice",
    "reset_work_dirs",
    "safe_join",
    "save_proposals",
    "session_path",
    "session_view",
    "stage_uploads",
    "work_path",
    "write_meta",
    "write_output_text",
    "write_script",
]

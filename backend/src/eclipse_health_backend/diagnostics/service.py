"""构造诊断 ZIP。

只包含版本、运行环境、数据量与脱敏后的日志；绝不包含波形、notes、payload、
成员姓名或绝对路径中的用户名。日志读取失败时降级为空，不影响诊断包生成。
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import re
import sys
import tempfile
import zipfile
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from sqlmodel import Session

from ..analysis.ids import rfc3339
from ..db.base import applied_migrations
from ..domain.common import utc_now
from ..privacy.service import storage_info
from ..settings import get_settings
from .logging_setup import logs_dir

_PER_FILE_LIMIT = 200 * 1024
_TOTAL_LOG_LIMIT = 512 * 1024
_MAX_LOG_FILES = 8


def _candidate_user_names() -> set[str]:
    names = {
        getpass.getuser(),
        Path.home().name,
        os.environ.get("USERNAME", ""),
        os.environ.get("USER", ""),
    }
    return {name for name in names if len(name) >= 3}


def redact(text: str, data_dir: Path | None = None) -> str:
    """去掉绝对路径中的用户名与数据目录。"""
    if data_dir is not None:
        text = text.replace(str(data_dir), "<data>")
    home = str(Path.home())
    if home:
        text = text.replace(home, "<user>")
    for name in _candidate_user_names():
        pattern = re.compile(
            rf"(?i)(users[\\/]|home[\\/]){re.escape(name)}(?=[\\/\"'\s]|$)"
        )
        text = pattern.sub(r"\1<user>", text)
    text = re.sub(r"(?i)[A-Z]:\\Users\\[^\\\s\"']+", r"C:\\Users\\<user>", text)
    text = re.sub(r"/home/[^/\s\"']+", "/home/<user>", text)
    text = re.sub(r"/Users/[^/\s\"']+", "/Users/<user>", text)
    return text


def _tail(path: Path, limit: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit:
                handle.seek(size - limit)
            data = handle.read()
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _read_logs(data_dir: Path) -> tuple[str, list[str], bool]:
    directory = logs_dir(get_settings())
    if not directory.is_dir():
        return "no log files\n", [], False
    candidates = [path for path in directory.glob("*.log*") if path.is_file()]
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    candidates = candidates[:_MAX_LOG_FILES]

    chunks: list[str] = []
    used = 0
    truncated = False
    files: list[str] = []
    for path in candidates:
        remaining = _TOTAL_LOG_LIMIT - used
        if remaining <= 0:
            truncated = True
            break
        text = _tail(path, min(_PER_FILE_LIMIT, remaining))
        if not text:
            continue
        if len(text.encode("utf-8", errors="replace")) >= remaining:
            truncated = True
        chunks.append(f"===== {path.name} =====\n{text.rstrip()}\n")
        used += len(text.encode("utf-8", errors="replace"))
        files.append(path.name)
    if not chunks:
        return "no recent log entries\n", files, truncated
    return redact("".join(chunks), data_dir), files, truncated


def _onnxruntime_version() -> str | None:
    try:
        return metadata.version("onnxruntime")
    except metadata.PackageNotFoundError:
        return None


def _system_info(data_dir: Path) -> str:
    lines = [
        f"app: eclipse health {get_settings().version}",
        f"python: {platform.python_version()} ({sys.implementation.name})",
        f"pythonExecutable: {redact(sys.executable, data_dir)}",
        f"platform: {platform.platform(aliased=True)}",
        f"machine: {platform.machine()}",
        f"processor: {platform.processor() or 'unknown'}",
        f"cpuCount: {os.cpu_count()}",
        f"dataDir: {redact(str(data_dir), data_dir)}",
        f"utcNow: {datetime.now().astimezone().isoformat()}",
    ]
    return "\n".join(lines) + "\n"


def _diagnostics_json(session: Session, data_dir: Path) -> dict[str, Any]:
    from ..privacy.settings_store import load_settings

    storage = storage_info(session)
    migrations = applied_migrations()
    storage_data = {
        "dataDir": redact(str(data_dir), data_dir),
        "counts": storage["counts"],
        "bytes": storage["bytes"],
    }
    settings = load_settings()
    return {
        "generatedAt": rfc3339(utc_now()),
        "app": {"name": "eclipse health", "version": get_settings().version},
        "runtime": {
            "python": platform.python_version(),
            "implementation": sys.implementation.name,
            "platform": platform.platform(aliased=True),
            "machine": platform.machine(),
            "cpuCount": os.cpu_count(),
        },
        "database": {
            "schemaVersion": migrations[-1] if migrations else None,
            "migrations": migrations,
        },
        "engine": {"onnxruntime": _onnxruntime_version()},
        "storage": storage_data,
        "settings": {
            "closeToTray": bool(settings.get("closeToTray")),
            "splashEnabled": bool(settings.get("splashEnabled")),
            "telemetryEnabled": False,
        },
    }


def build_diagnostics_bundle(session: Session) -> Path:
    settings = get_settings()
    data_dir = settings.data_dir
    logs_text, log_files, truncated = _read_logs(data_dir)
    payload = _diagnostics_json(session, data_dir)
    payload["logs"] = {"files": log_files, "truncated": truncated}

    fd, name = tempfile.mkstemp(prefix="eh-diagnostics-", suffix=".zip")
    os.close(fd)
    path = Path(name)
    try:
        with zipfile.ZipFile(
            path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as zf:
            zf.writestr(
                "diagnostics.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            zf.writestr("system.txt", _system_info(data_dir))
            zf.writestr("logs.txt", logs_text)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


__all__ = ["build_diagnostics_bundle", "redact"]

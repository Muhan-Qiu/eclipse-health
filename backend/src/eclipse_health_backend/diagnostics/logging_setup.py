"""把日志同时写到 ``data/logs/backend.log``，供诊断包读取。

只加一个 RotatingFileHandler，不改变现有的控制台格式；重复调用不会重复挂载。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..settings import Settings

_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3


def logs_dir(settings: Settings) -> Path:
    return settings.data_dir / "logs"


def install_file_logging(settings: Settings) -> None:
    directory = logs_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / "backend.log").resolve()

    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            try:
                if Path(handler.baseFilename).resolve() == target:
                    return
            except OSError:
                continue

    handler = RotatingFileHandler(
        target,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.setLevel(settings.normalize_log_level())
    root.addHandler(handler)


__all__ = ["install_file_logging", "logs_dir"]

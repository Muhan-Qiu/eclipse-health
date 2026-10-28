"""应用配置。

所有路径都从 ``EH_DATA_DIR`` 派生，测试只需在导入应用前设置这个环境变量。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import __version__

# backend/src/eclipse_health_backend/settings.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]

LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EH_", extra="ignore")

    app_name: str = "eclipse health backend"
    version: str = __version__

    # 默认 <repo>/backend/.data；测试用 EH_DATA_DIR 覆盖，避免污染真实数据。
    data_dir: Path = Field(default=BACKEND_ROOT / ".data")

    port: int = Field(default=8765, ge=1, le=65535)
    log_level: str = "INFO"

    # 只放行本机来源：Vite dev server、Tauri webview、本地回环任意端口。
    cors_origin_regex: str = (
        r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?"
        r"|tauri://localhost|https?://tauri\.localhost)$"
    )

    # 内联 JSON 波形上限；更大的数据必须走 fileRef。
    signal_inline_max_samples: int = 2_000_000
    # 单个信号文件上限，Schema §12「单条记录波形 ≤2GB」在核心层先按字节兜底。
    signal_max_bytes: int = 2 * 1024 * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / "eclipse_health.sqlite3"

    @property
    def signals_dir(self) -> Path:
        return self.data_dir / "signals"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    # 导入文件只允许放在这里，避免用户输入直接变成任意路径。
    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.signals_dir, self.reports_dir, self.imports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def normalize_log_level(self) -> int:
        level = self.log_level.upper()
        if level not in LOG_LEVELS:
            level = "INFO"
        return getattr(logging, level)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

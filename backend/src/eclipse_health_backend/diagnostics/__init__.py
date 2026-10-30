"""诊断包：版本、运行环境、最近日志（已脱敏）。"""

from __future__ import annotations

from .logging_setup import install_file_logging
from .service import build_diagnostics_bundle

__all__ = ["build_diagnostics_bundle", "install_file_logging"]

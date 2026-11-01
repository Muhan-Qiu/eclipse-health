"""Cardia 2.0 单导联心电分析库（B1）。

对外只暴露纯函数式接口；不依赖 FastAPI、数据库或模块系统。
"""

from __future__ import annotations

from .engine import analyze
from .ids import new_id, rfc3339, utcnow, uuid7
from .ingest import ingest, load_array, load_csv, load_npy, load_wfdb, resample_signal
from .types import (
    DEFAULT_MODEL_DIR,
    SCHEMA_ANALYSIS,
    SCHEMA_MEASUREMENT,
    TARGET_FS,
    AnalysisError,
    AnalysisOptions,
    EcgSignal,
    InsufficientBeatsError,
    InvalidSignalError,
    ModelLoadError,
)

__all__ = [
    "DEFAULT_MODEL_DIR",
    "SCHEMA_ANALYSIS",
    "SCHEMA_MEASUREMENT",
    "TARGET_FS",
    "AnalysisError",
    "AnalysisOptions",
    "EcgSignal",
    "InsufficientBeatsError",
    "InvalidSignalError",
    "ModelLoadError",
    "analyze",
    "ingest",
    "load_array",
    "load_csv",
    "load_npy",
    "load_wfdb",
    "new_id",
    "resample_signal",
    "rfc3339",
    "utcnow",
    "uuid7",
]

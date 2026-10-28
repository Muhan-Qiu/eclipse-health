"""分析引擎的公共类型。

设计约束（见 ``prompts/03-cardia-engine.md`` §5）：
输入输出都是普通 Python 对象，可 JSON 序列化，不依赖 FastAPI 或数据库。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .ids import new_id, utcnow

SCHEMA_ANALYSIS = "org.eclipsehealth.analysis/1"
SCHEMA_MEASUREMENT = "org.eclipsehealth.measurement/1"

# backend/src/eclipse_health_backend/analysis/types.py -> backend/resources/models/cardia
DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parents[3] / "resources" / "models" / "cardia"
)
TARGET_FS = 360.0
# MIT-BIH MLII 的 ADC 增益；非 WFDB 输入按此映射到 Cardia 特征尺度。
DEFAULT_FEATURE_GAIN = 200.0


class AnalysisError(Exception):
    """分析链路的业务错误基类。"""


class InvalidSignalError(AnalysisError):
    """信号本身不合法（空、NaN、常量、采样率非法等）。"""


class InsufficientBeatsError(InvalidSignalError):
    """有效心搏不足，无法组成模型输入。"""


class ModelLoadError(AnalysisError):
    """模型或预处理文件缺失、损坏、彼此不一致。"""


@dataclass
class EcgSignal:
    """统一的心电输入。

    ``samples`` 是物理单位 mV、目标采样率下的 float32 波形；
    ``digital`` 是同一时间轴的 ADC 数字量，Cardia 2.0 的 104 维特征吃数字量
    （与 V2 的 ``physical=False`` 路径一致），没有时由 ``samples * gain`` 近似。
    """

    samples: np.ndarray
    fs: float
    lead: str = "unknown"
    source: str = "array"
    original_fs: float | None = None
    resampled: bool = False
    digital: np.ndarray | None = None
    gain: float | None = None
    annotations: list[tuple[int, str]] | None = None
    record_name: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        samples = np.array(self.samples, dtype=np.float32, copy=True)
        if samples.ndim != 1:
            raise InvalidSignalError(
                f"samples 必须是一维数组，实际 shape={samples.shape}"
            )
        if samples.size == 0:
            raise InvalidSignalError("samples 为空")
        if not np.isfinite(samples).all():
            raise InvalidSignalError("samples 含 NaN/Inf")
        try:
            fs = float(self.fs)
        except (TypeError, ValueError) as exc:
            raise InvalidSignalError(f"采样率非法：{self.fs!r}") from exc
        if not np.isfinite(fs) or fs <= 0:
            raise InvalidSignalError(f"采样率必须为正数，实际 {fs!r}")
        if float(np.std(samples)) < 1e-9:
            raise InvalidSignalError("信号为常量，疑似导联脱落或数据损坏")

        digital = None
        if self.digital is not None:
            digital = np.array(self.digital, dtype=np.float64, copy=True)
            if digital.ndim != 1 or digital.size != samples.size:
                raise InvalidSignalError("digital 必须与 samples 等长且为一维")
            if not np.isfinite(digital).all():
                raise InvalidSignalError("digital 含 NaN/Inf")

        annotations = None
        if self.annotations is not None:
            annotations = sorted(
                (int(pos), str(sym)) for pos, sym in self.annotations
            )
            if annotations and (
                annotations[0][0] < 0 or annotations[-1][0] >= samples.size
            ):
                raise InvalidSignalError("标注位置超出信号范围")

        self.samples = samples
        self.fs = fs
        self.original_fs = float(self.original_fs) if self.original_fs else fs
        self.resampled = bool(self.resampled)
        self.digital = digital
        self.annotations = annotations
        self.lead = str(self.lead or "unknown")
        self.source = str(self.source or "array")
        self.warnings = list(self.warnings or [])

    @property
    def n_samples(self) -> int:
        return int(self.samples.size)

    @property
    def duration_sec(self) -> float:
        return self.n_samples / self.fs

    def to_dict(self) -> dict[str, Any]:
        """只输出元数据，绝不包含波形（隐私与体积）。"""
        return {
            "fs": self.fs,
            "originalFs": self.original_fs,
            "resampled": self.resampled,
            "lead": self.lead,
            "source": self.source,
            "nSamples": self.n_samples,
            "durationSec": round(self.duration_sec, 6),
            "gain": self.gain,
            "hasAnnotations": bool(self.annotations),
            "annotationCount": len(self.annotations or []),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class AnalysisOptions:
    """``analyze()`` 的可调参数。

    ``record_id`` 由调用方提供（``rec_...`` 或临时 ID），引擎不查库、不生成记录。
    """

    record_id: str
    module_id: str = "org.eclipsehealth.cardia"
    model_id: str = "cardia-2.0"
    model_version: str = "2.0.0"
    model_dir: Path | None = None
    analysis_id: str | None = None
    allow_short_record: bool = False
    tail_mode: str = "pad"
    max_inline_beats: int = 50_000
    rpeak_method: str = "neurokit"
    id_factory: Callable[[str], str] = new_id
    clock: Callable[[], datetime] = utcnow

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id 不能为空，需由调用方提供")
        if self.tail_mode not in {"pad", "drop"}:
            raise ValueError("tail_mode 只能是 'pad' 或 'drop'")
        if self.max_inline_beats < 1:
            raise ValueError("max_inline_beats 必须为正整数")
        if self.model_dir is not None:
            self.model_dir = Path(self.model_dir)

    def make_id(self, prefix: str) -> str:
        return str(self.id_factory(prefix))


def coerce_signal(value: EcgSignal | Mapping[str, Any]) -> EcgSignal:
    """接受 EcgSignal 或普通 dict，便于模块系统直接调用。"""
    if isinstance(value, EcgSignal):
        return value
    if isinstance(value, Mapping):
        data = dict(value)
        if "originalFs" in data and "original_fs" not in data:
            data["original_fs"] = data.pop("originalFs")
        return EcgSignal(**data)
    raise TypeError("signal 必须是 EcgSignal 或 dict")


def coerce_options(value: AnalysisOptions | Mapping[str, Any]) -> AnalysisOptions:
    if isinstance(value, AnalysisOptions):
        return value
    if isinstance(value, Mapping):
        return AnalysisOptions(**dict(value))
    raise TypeError("options 必须是 AnalysisOptions 或 dict")

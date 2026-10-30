"""适配器契约与公共类型。

文件所有权：本包只被 ``importers.api`` 与测试引用；不修改核心模块。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

UNIT_TO_MV: dict[str, float] = {"mV": 1.0, "uV": 0.001, "nV": 0.000001, "V": 1000.0}

LEAD_ALIASES: dict[str, str] = {
    "mlii": "MLII",
    "mlii1": "MLII",
    "ml ii": "MLII",
    "mlleadii": "MLII",
    "i": "I",
    "ii": "II",
    "iii": "III",
    "avr": "aVR",
    "avl": "aVL",
    "avf": "aVF",
    "v1": "V1",
    "v2": "V2",
    "v3": "V3",
    "v4": "V4",
    "v5": "V5",
    "v6": "V6",
    "ecg": "ECG",
    "ekg": "ECG",
    "心电": "ECG",
}

_UNIT_RE = re.compile(
    r"[\(\[]\s*(mv|uv|µv|μv|nv|v|millivolt|microvolt|nanovolt|volt)\s*[\)\]]", re.IGNORECASE
)
_LEAD_SANITIZE_RE = re.compile(r"[^A-Za-z0-9+\-]")

TARGET_FS = 360.0


def warning(code: str, message: str, severity: str = "info") -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def normalize_unit(unit: str | None) -> str | None:
    """把常见写法归一成 mV / uV / V；未知单位返回 None（不硬猜）。"""
    if not unit:
        return None
    key = str(unit).strip().lower().strip(".")
    if key in {"mv", "millivolt", "millivolts"}:
        return "mV"
    if key in {"uv", "µv", "μv", "microvolt", "microvolts"}:
        return "uV"
    if key in {"nv", "nanovolt", "nanovolts"}:
        return "nV"
    if key in {"v", "volt", "volts"}:
        return "V"
    return None


def unit_scale(unit: str | None) -> float | None:
    normalized = normalize_unit(unit)
    if normalized is None:
        return None
    return UNIT_TO_MV[normalized]


def detect_unit_in_text(text: str) -> str | None:
    """从列名/表头里提取单位标注，如 ``ECG (mV)``、``voltage[uV]``。"""
    match = _UNIT_RE.search(str(text or ""))
    if match:
        return normalize_unit(match.group(1))
    return None


def normalize_lead_name(name: str | None, index: int = 0) -> str:
    """保留标准导联名；其余去掉单位后缀并限制在 Schema 的导联字符集内。"""
    raw = _UNIT_RE.sub(" ", str(name or "")).strip()
    raw = re.sub(r"\s+", " ", raw)
    key = raw.lower().replace(" ", "")
    alias = LEAD_ALIASES.get(key)
    if alias:
        return alias
    sanitized = _LEAD_SANITIZE_RE.sub("", raw.split()[0] if raw else "")
    if not sanitized:
        return f"L{index + 1}"
    if not sanitized[0].isalpha():
        sanitized = f"L{sanitized}"
    return sanitized[:16]


@dataclass(slots=True)
class Detection:
    format: str
    confidence: float
    reason: str


@dataclass(slots=True)
class ImportSource:
    """一次预览/提交的输入。

    ``path`` 对上传文件是工作区里的副本，对 ``path`` 调试参数是用户给的绝对路径；
    ``extracted_dir`` 仅在 ZIP 解压成功后存在。
    """

    kind: str
    path: Path
    workspace: Path
    original_name: str | None = None
    file_name_hash: str = ""
    file_hash: str = ""
    extracted_dir: Path | None = None
    # ZIP 被加密时无法解压；适配器可据此给出 ``encrypted_export``。
    encrypted: bool = False

    @property
    def uploaded(self) -> bool:
        return self.kind == "upload"


@dataclass(slots=True)
class ParseParameters:
    """预览无参数；提交时可校正采样率/导联/单位/极性。"""

    sampling_rate: float | None = None
    lead: str | None = None
    unit: str | None = None
    polarity: str = "normal"
    lead_column: str | None = None
    time_column: str | None = None


@dataclass(slots=True)
class ParsedLead:
    lead: str
    samples: np.ndarray
    digital: np.ndarray | None = None
    gain: float = 200.0


@dataclass(slots=True)
class HealthRecordDraft:
    """非波形健康数据（步数/心率/睡眠/体重/血压）。

    ``payload`` 按 DATA_SCHEMA 约定保存 ``{value, unit, startAt, endAt, sourceApp?}``；
    ``external_id`` 是去重键（Apple 导出无 UUID 时用字段指纹）。
    """

    record_type: str
    kind: str
    payload: dict[str, Any]
    captured_at: datetime
    external_id: str
    unit: str = "1"
    duration_sec: float | None = None
    source_app: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedImport:
    adapter_id: str
    adapter_version: str
    format: str
    sampling_rate: float
    duration_sec: float
    leads: list[ParsedLead]
    primary_lead: str
    source_unit: str = "mV"
    has_annotations: bool = False
    annotation_count: int = 0
    # .atr 参考标注 (sample, symbol)；只用于复用 R 峰，不作为诊断标签。
    reference_annotations: list[tuple[int, str]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    # 健康数据包（Apple / 小米）：多条非波形记录 + 多条 ECG 子记录。
    health_records: list[HealthRecordDraft] = field(default_factory=list)
    ecg_records: list[ParsedImport] = field(default_factory=list)
    captured_at: datetime | None = None
    record_counts: dict[str, int] = field(default_factory=dict)
    total_records: int = 0
    import_source: str | None = None

    @property
    def is_bundle(self) -> bool:
        return bool(self.health_records or self.ecg_records)

    @property
    def reference_r_peaks(self) -> list[int] | None:
        if not self.reference_annotations:
            return None
        return [int(pos) for pos, _symbol in self.reference_annotations]

    def to_ecg_signals(self) -> list[Any]:
        """把解析结果转成 B1-03 的 EcgSignal，便于直接调用 ``analysis.analyze``。"""
        from ..analysis.types import EcgSignal

        signals = []
        for lead in self.leads:
            annotations = (
                list(self.reference_annotations)
                if lead.lead == self.primary_lead and self.reference_annotations
                else None
            )
            signals.append(
                EcgSignal(
                    samples=lead.samples,
                    fs=self.sampling_rate,
                    lead=lead.lead,
                    source=self.format,
                    digital=lead.digital,
                    gain=lead.gain,
                    annotations=annotations,
                    warnings=list(self.warnings),
                )
            )
        return signals


@dataclass(slots=True)
class PreviewData:
    sampling_rate: float | None
    leads: list[str]
    duration_sec: float | None
    unit: str
    requires_sampling_rate: bool
    requires_lead: bool
    requires_unit: bool
    warnings: list[dict[str, Any]]
    n_samples: int | None
    samples: list[float]
    has_annotations: bool = False
    annotation_count: int = 0
    # 健康数据包按类型的记录数（steps/heartRate/sleep/bodyMass/bloodPressure/ecg）。
    record_counts: dict[str, int] = field(default_factory=dict)
    total_records: int = 0

    @property
    def requires(self) -> dict[str, bool]:
        return {
            "samplingRate": self.requires_sampling_rate,
            "lead": self.requires_lead,
            "unit": self.requires_unit,
        }


def finalize_parsed(parsed: ParsedImport, parameters: ParseParameters) -> ParsedImport:
    """应用采样率校正、导联重命名与极性翻转；单位换算在适配器内完成。"""
    if parameters.sampling_rate is not None:
        rate = float(parameters.sampling_rate)
        if rate <= 0:
            from .errors import invalid_file

            raise invalid_file("采样率必须为正数", details={"samplingRate": rate})
        parsed.sampling_rate = rate
        if parsed.leads:
            parsed.duration_sec = parsed.leads[0].samples.size / rate

    if parameters.polarity == "inverted":
        for lead in parsed.leads:
            lead.samples = -np.asarray(lead.samples, dtype=np.float64)
            if lead.digital is not None:
                lead.digital = -np.asarray(lead.digital, dtype=np.float64)
        parsed.metadata["polarity"] = "inverted"
        parsed.warnings.append(
            warning("polarity_inverted", "按用户参数翻转了波形极性", severity="info")
        )

    if parameters.lead:
        renamed = normalize_lead_name(parameters.lead, 0)
        for lead in parsed.leads:
            if lead.lead == parsed.primary_lead:
                lead.lead = renamed
        parsed.primary_lead = renamed

    seen: dict[str, int] = {}
    for lead in parsed.leads:
        count = seen.get(lead.lead, 0)
        seen[lead.lead] = count + 1
        if count:
            lead.lead = f"{lead.lead[:14]}-{count + 1}"
    return parsed


class ImportAdapter(ABC):
    """所有格式适配器的统一接口；厂商格式留位见 ``placeholders``。"""

    adapter_id: ClassVar[str] = ""
    adapter_version: ClassVar[str] = "1.0.0"
    format: ClassVar[str] = ""
    supported: ClassVar[bool] = True

    @abstractmethod
    def detect(self, source: ImportSource) -> Detection | None:
        """返回置信度（0–1）；0 表示不是本格式。"""

    @abstractmethod
    def preview(self, source: ImportSource) -> PreviewData:
        """只解析元数据与前 2000 点，供用户确认参数。"""

    @abstractmethod
    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        """完整解析并应用校正参数。"""

    def info(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "format": self.format,
            "supported": self.supported,
            "adapterVersion": self.adapter_version,
        }


__all__ = [
    "LEAD_ALIASES",
    "TARGET_FS",
    "UNIT_TO_MV",
    "Detection",
    "HealthRecordDraft",
    "ImportAdapter",
    "ImportSource",
    "ParseParameters",
    "ParsedImport",
    "ParsedLead",
    "PreviewData",
    "detect_unit_in_text",
    "finalize_parsed",
    "normalize_lead_name",
    "normalize_unit",
    "unit_scale",
    "warning",
]

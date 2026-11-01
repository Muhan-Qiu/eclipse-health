"""EDF / EDF+ 适配器（标准库 + numpy，不引入新依赖）。

只依赖公开格式规范：
- 256 字节固定头 + 每信号 256 字节定义；
- 物理值 = (digital - dmin) * (pmax - pmin) / (dmax - dmin) + pmin；
- 数据记录交错存放，按每信号每记录的采样数切片。

EDF 没有时区信息，起始时间只作为元数据记录，入库时间仍由用户确认。
``EDF Annotations`` 通道只统计标注数量，不当作诊断标签或 R 峰位置。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .base import (
    LEAD_ALIASES,
    TARGET_FS,
    Detection,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    finalize_parsed,
    normalize_lead_name,
    normalize_unit,
    unit_scale,
    warning,
)
from .errors import ImportApiError, invalid_file

FIXED_HEADER = 256
SIGNAL_HEADER = 256
MAX_PREVIEW_SAMPLES = 2000
ANNOTATION_LABEL = "edf annotations"
_LEAD_SHAPE_RE = re.compile(r"^(?:mlii|i{1,3}|av[rlf]|v[1-6])$")
_LEAD_PREFIX_RE = re.compile(r"^\s*(?:ecg|ekg|lead)[\s_\-:]*", re.IGNORECASE)


@dataclass(slots=True)
class EdfSignal:
    label: str
    transducer: str
    dimension: str
    phys_min: float
    phys_max: float
    dig_min: float
    dig_max: float
    prefilter: str
    samples_per_record: int
    annotation: bool = False
    malformed: bool = False

    @property
    def slope(self) -> float:
        return (self.phys_max - self.phys_min) / (self.dig_max - self.dig_min)


@dataclass(slots=True)
class EdfHeader:
    version: str
    patient_id: str
    recording_id: str
    start_time: str | None
    header_bytes: int
    record_duration: float
    declared_records: int
    signals: list[EdfSignal] = field(default_factory=list)


@dataclass(slots=True)
class EdfRecord:
    path: Path
    header: EdfHeader
    raw: np.memmap
    n_records: int
    imported: list[int]
    primary: int
    leads: dict[int, str]
    sampling_rate: float
    warnings: list[dict[str, Any]]
    annotation_count: int

    @property
    def duration(self) -> float:
        return self.n_records * self.header.record_duration

    def n_samples(self, index: int) -> int:
        return self.n_records * self.header.signals[index].samples_per_record

    def digital(self, index: int, limit: int | None = None) -> np.ndarray:
        signal = self.header.signals[index]
        per_record = signal.samples_per_record
        start = sum(s.samples_per_record for s in self.header.signals[:index])
        rows = self.n_records if limit is None else min(
            self.n_records, math.ceil(limit / max(per_record, 1))
        )
        block = np.array(self.raw[:rows, start : start + per_record], copy=True).reshape(-1)
        if limit is not None:
            return block[:limit]
        return block


def _text(blob: bytes) -> str:
    return blob.decode("latin-1", errors="replace").strip()


def _number(blob: bytes, field_name: str) -> float:
    raw = _text(blob)
    try:
        value = float(raw)
    except ValueError:
        raise invalid_file(
            "EDF 头部字段不是数字",
            details={"field": field_name, "value": raw[:32]},
        ) from None
    if not math.isfinite(value):
        raise invalid_file("EDF 头部字段不是有限数值", details={"field": field_name})
    return value


def _integer(blob: bytes, field_name: str) -> int:
    raw = _text(blob)
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            raise invalid_file(
                "EDF 头部字段不是整数",
                details={"field": field_name, "value": raw[:32]},
            ) from None


def _slice(blob: bytes, start: int, width: int) -> bytes:
    return blob[start : start + width]


def _parse_start_time(date_text: str, time_text: str) -> str | None:
    try:
        day, month, year = (int(part) for part in date_text.split("."))
        hour, minute, second = (int(part) for part in time_text.split("."))
        full_year = 1900 + year if year >= 85 else 2000 + year
        return datetime(full_year, month, day, hour, minute, second).isoformat()
    except (ValueError, TypeError):
        return None


def _lead_from_label(label: str, index: int) -> str:
    prefix = _LEAD_PREFIX_RE.match(label)
    rest = label[prefix.end() :].strip() if prefix else label.strip()
    compact = re.sub(r"[^a-z0-9]", "", rest.lower())
    if not compact:
        return "ECG"
    if compact.isdigit():
        # ECG1/ECG2 这类单导联通道名，不把数字当导联名。
        return "ECG"
    if compact in LEAD_ALIASES:
        return LEAD_ALIASES[compact]
    if _LEAD_SHAPE_RE.match(compact):
        return LEAD_ALIASES.get(compact, normalize_lead_name(rest, index))
    return normalize_lead_name(rest, index)


def _is_ecg_label(label: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", label.lower())
    if compact.startswith(("ecg", "ekg")):
        return True
    return compact in LEAD_ALIASES or bool(_LEAD_SHAPE_RE.match(compact))


def _count_annotations(block: np.ndarray) -> int:
    """TAL 以 ``\\x00`` 分隔；只统计带文本的标注，时间事件不算。"""
    payload = np.asarray(block, dtype="<i2").tobytes()
    count = 0
    for chunk in payload.split(b"\x00"):
        if b"\x14" not in chunk:
            continue
        parts = chunk.split(b"\x14")
        if any(part.strip() for part in parts[1:]):
            count += 1
    return count


class EdfImportAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.edf"
    adapter_version = "1.0.0"
    format = "edf"

    # ---------------------------------------------------------------- detect
    def _candidates(self, source: ImportSource) -> list[Path]:
        def _files(root: Path) -> list[Path]:
            return sorted(
                path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".edf"
            )

        if source.extracted_dir is not None:
            return _files(source.extracted_dir)
        if source.path.is_dir():
            return _files(source.path)
        if source.path.suffix.lower() == ".edf":
            return [source.path]
        return []

    @staticmethod
    def _magic(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                head = handle.read(FIXED_HEADER)
        except OSError:
            return False
        if len(head) < FIXED_HEADER or head[:1] != b"0":
            return False
        try:
            header_bytes = _integer(head[184:192], "headerBytes")
            signals = _integer(head[252:256], "signals")
        except ImportApiError:
            return False
        return 256 + SIGNAL_HEADER * signals <= header_bytes <= 1_000_000

    def detect(self, source: ImportSource) -> Detection | None:
        candidates = self._candidates(source)
        if candidates:
            return Detection(self.format, 1.0, "扩展名为 .edf")
        if source.path.is_file() and self._magic(source.path):
            return Detection(self.format, 0.85, "内容符合 EDF 固定头特征")
        return None

    def _pick_file(self, source: ImportSource) -> Path:
        candidates = self._candidates(source)
        if not candidates and source.path.is_file() and self._magic(source.path):
            return source.path
        if not candidates:
            raise invalid_file("未找到 EDF 文件")
        if len(candidates) > 1:
            raise invalid_file(
                "目录或压缩包里有多个 EDF 文件，请只保留一个",
                details={"candidates": [item.name for item in candidates]},
            )
        return candidates[0]

    # ---------------------------------------------------------------- header
    def _read_header(self, path: Path) -> EdfHeader:
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise invalid_file("无法读取 EDF 文件", details={"reason": str(exc)}) from exc
        if len(blob) < FIXED_HEADER:
            raise invalid_file("EDF 文件短于 256 字节固定头")
        version = _text(_slice(blob, 0, 8))
        if not version.startswith("0"):
            raise invalid_file("EDF 版本字段非法", details={"version": version[:8]})
        header_bytes = _integer(_slice(blob, 184, 8), "headerBytes")
        declared_records = _integer(_slice(blob, 236, 8), "dataRecords")
        record_duration = _number(_slice(blob, 244, 8), "recordDuration")
        signals = _integer(_slice(blob, 252, 4), "signals")
        if signals <= 0 or signals > 256:
            raise invalid_file("EDF 信号数量非法", details={"signals": signals})
        if record_duration <= 0:
            raise invalid_file(
                "EDF 每条数据记录时长必须为正",
                details={"recordDuration": record_duration},
            )
        required = FIXED_HEADER + SIGNAL_HEADER * signals
        if header_bytes < required:
            raise invalid_file(
                "EDF 头部长度小于信号定义所需",
                details={"headerBytes": header_bytes, "required": required},
            )
        if header_bytes > len(blob):
            raise invalid_file(
                "EDF 头部被截断",
                details={"headerBytes": header_bytes, "bytes": len(blob)},
            )

        base = FIXED_HEADER
        widths = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
        offsets: list[int] = []
        cursor = base
        for width in widths:
            offsets.append(cursor)
            cursor += width * signals

        def field(index: int, column: int) -> bytes:
            return _slice(blob, offsets[column] + index * widths[column], widths[column])

        parsed: list[EdfSignal] = []
        for index in range(signals):
            samples = _integer(field(index, 8), f"signal[{index}].samples")
            if samples <= 0:
                raise invalid_file(
                    "EDF 信号每记录采样数必须为正",
                    details={"signal": index, "samples": samples},
                )
            label = _text(field(index, 0))
            annotation = label.strip().lower() == ANNOTATION_LABEL
            malformed = False
            try:
                dimension = _text(field(index, 2))
                phys_min = _number(field(index, 3), f"signal[{index}].physMin")
                phys_max = _number(field(index, 4), f"signal[{index}].physMax")
                dig_min = _number(field(index, 5), f"signal[{index}].digMin")
                dig_max = _number(field(index, 6), f"signal[{index}].digMax")
                if dig_max == dig_min:
                    raise invalid_file(
                        "EDF 信号的数字量范围为零",
                        details={"signal": index, "label": label[:32]},
                    )
            except ImportApiError:
                # 非 ECG 通道的换算字段可能为空；跳过该通道而不是整文件失败。
                if not annotation and not _is_ecg_label(label):
                    dimension = _text(field(index, 2))
                    phys_min, phys_max, dig_min, dig_max = 0.0, 1.0, 0.0, 1.0
                    malformed = True
                else:
                    raise
            parsed.append(
                EdfSignal(
                    label=label,
                    transducer=_text(field(index, 1)),
                    dimension=dimension,
                    phys_min=phys_min,
                    phys_max=phys_max,
                    dig_min=dig_min,
                    dig_max=dig_max,
                    prefilter=_text(field(index, 7)),
                    samples_per_record=samples,
                    annotation=annotation,
                    malformed=malformed,
                )
            )

        return EdfHeader(
            version=version,
            patient_id=_text(_slice(blob, 8, 80)),
            recording_id=_text(_slice(blob, 88, 80)),
            start_time=_parse_start_time(_text(_slice(blob, 168, 8)), _text(_slice(blob, 176, 8))),
            header_bytes=header_bytes,
            record_duration=record_duration,
            declared_records=declared_records,
            signals=parsed,
        )

    # ------------------------------------------------------------- analysis
    def _analyze(self, source: ImportSource) -> EdfRecord:
        path = self._pick_file(source)
        header = self._read_header(path)
        warnings: list[dict[str, Any]] = []

        ecg_indexes = [
            index for index, signal in enumerate(header.signals) if not signal.annotation and _is_ecg_label(signal.label)
        ]
        malformed_other = [
            signal.label[:32]
            for signal in header.signals
            if signal.malformed and not signal.annotation and not _is_ecg_label(signal.label)
        ]
        if malformed_other:
            warnings.append(
                warning(
                    "channel_invalid_bounds",
                    "部分非 ECG 通道缺少有效量程，已跳过：" + ", ".join(malformed_other),
                    severity="warning",
                )
            )
        if not ecg_indexes:
            raise invalid_file(
                "EDF 中没有标注为 ECG/MLII/标准导联的通道",
                details={"labels": [signal.label[:32] for signal in header.signals]},
            )

        rates = {
            index: header.signals[index].samples_per_record / header.record_duration
            for index in ecg_indexes
        }
        preferred = next(
            (
                index
                for wanted in ("MLII", "II", "I")
                for index in ecg_indexes
                if _lead_from_label(header.signals[index].label, index) == wanted
            ),
            ecg_indexes[0],
        )
        primary_rate = rates[preferred]
        imported = [index for index in ecg_indexes if abs(rates[index] - primary_rate) < 1e-6]
        skipped = [index for index in ecg_indexes if index not in imported]
        if skipped:
            warnings.append(
                warning(
                    "channel_rate_mismatch",
                    "部分 ECG 通道采样率与主通道不同，已跳过："
                    + ", ".join(header.signals[index].label[:32] for index in skipped),
                    severity="warning",
                )
            )

        record_samples = sum(signal.samples_per_record for signal in header.signals)
        record_bytes = record_samples * 2
        data_bytes = path.stat().st_size - header.header_bytes
        if data_bytes < record_bytes:
            raise invalid_file(
                "EDF 没有完整的数据记录",
                details={"bytes": max(data_bytes, 0), "recordBytes": record_bytes},
            )
        available = data_bytes // record_bytes
        declared = header.declared_records
        if declared < 0:
            n_records = available
        elif declared == 0:
            n_records = available
            warnings.append(
                warning("record_count_missing", "EDF 头未写数据记录数，按文件长度推算", severity="warning")
            )
        else:
            n_records = min(declared, available)
            if declared > available:
                warnings.append(
                    warning(
                        "truncated_records",
                        f"EDF 头声明 {declared} 条记录，文件只有 {available} 条，已按实际读取",
                        severity="warning",
                    )
                )
        if n_records <= 0:
            raise invalid_file("EDF 没有可读取的数据记录")
        remainder = data_bytes - n_records * record_bytes
        if remainder > 0:
            warnings.append(
                warning("trailing_bytes", f"EDF 末尾有 {remainder} 字节不属于完整记录，已忽略")
            )

        raw = np.memmap(
            path,
            dtype="<i2",
            mode="r",
            offset=header.header_bytes,
            shape=(n_records, record_samples),
        )

        annotation_count = 0
        for index, signal in enumerate(header.signals):
            if signal.annotation:
                start = sum(item.samples_per_record for item in header.signals[:index])
                block = np.asarray(raw[:, start : start + signal.samples_per_record])
                annotation_count += _count_annotations(block)

        leads = {
            index: _lead_from_label(header.signals[index].label, index) for index in imported
        }
        if len(imported) > 1:
            warnings.append(
                warning("multi_lead", f"文件含 {len(imported)} 个 ECG 导联，将全部入库", severity="info")
            )
        if abs(primary_rate - TARGET_FS) > 1e-6:
            warnings.append(
                warning(
                    "non_target_sampling_rate",
                    f"采样率 {primary_rate:g} Hz，分析引擎以 360 Hz 为基准，提交时需确认",
                    severity="warning",
                )
            )
        if header.start_time is None:
            warnings.append(
                warning("start_time_invalid", "EDF 起始日期/时间无法解析，入库时间以用户确认值为准")
            )

        return EdfRecord(
            path=path,
            header=header,
            raw=raw,
            n_records=n_records,
            imported=imported,
            primary=preferred,
            leads=leads,
            sampling_rate=primary_rate,
            warnings=warnings,
            annotation_count=annotation_count,
        )

    @staticmethod
    def _source_unit(signal: EdfSignal, parameters: ParseParameters | None = None) -> str | None:
        if parameters is not None and parameters.unit:
            return normalize_unit(parameters.unit)
        return normalize_unit(signal.dimension)

    def _physical(self, record: EdfRecord, index: int, limit: int | None = None) -> np.ndarray:
        signal = record.header.signals[index]
        digital = record.digital(index, limit).astype(np.float64)
        return (digital - signal.dig_min) * signal.slope + signal.phys_min

    # --------------------------------------------------------------- preview
    def preview(self, source: ImportSource) -> PreviewData:
        record = self._analyze(source)
        primary_signal = record.header.signals[record.primary]
        unit = self._source_unit(primary_signal)
        requires_unit = any(
            normalize_unit(record.header.signals[index].dimension) is None for index in record.imported
        )
        scale = unit_scale(unit) if unit else 1.0

        samples = self._physical(record, record.primary, MAX_PREVIEW_SAMPLES) * scale
        warnings = list(record.warnings)
        if requires_unit:
            warnings.append(
                warning(
                    "unknown_units",
                    "EDF 头里的物理单位不是 mV/uV/nV/V，提交时需指定各通道原始单位",
                    severity="warning",
                )
            )

        return PreviewData(
            sampling_rate=record.sampling_rate,
            leads=[record.leads[index] for index in record.imported],
            duration_sec=record.duration,
            unit="mV",
            requires_sampling_rate=False,
            requires_lead=False,
            requires_unit=requires_unit,
            warnings=warnings,
            n_samples=record.n_samples(record.primary),
            samples=[float(value) for value in samples],
            has_annotations=record.annotation_count > 0,
            annotation_count=record.annotation_count,
        )

    # ----------------------------------------------------------------- parse
    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        record = self._analyze(source)
        if parameters.unit and unit_scale(parameters.unit) is None:
            raise ImportApiError(
                "无法识别的单位参数（可用 mV/uV/V）",
                code="invalid_parameter",
                details={"unit": parameters.unit},
            )

        leads: list[ParsedLead] = []
        for index in record.imported:
            signal = record.header.signals[index]
            source_unit = self._source_unit(signal, parameters)
            if source_unit is None:
                raise ImportApiError(
                    "EDF 通道缺少可识别的物理单位，请用 parameters.unit 指定",
                    code="unit_required",
                    details={"channel": signal.label[:32], "dimension": signal.dimension[:16]},
                )
            scale = unit_scale(source_unit) or 1.0
            digital = record.digital(index)
            physical = (digital.astype(np.float64) - signal.dig_min) * signal.slope + signal.phys_min
            leads.append(
                ParsedLead(
                    lead=record.leads[index],
                    samples=physical * scale,
                    digital=digital,
                    gain=signal.slope * scale,
                )
            )

        primary_lead = record.leads[record.primary]
        primary_unit = self._source_unit(record.header.signals[record.primary], parameters) or "mV"
        warnings = list(record.warnings)
        parsed = ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=record.sampling_rate,
            duration_sec=record.duration,
            leads=leads,
            primary_lead=primary_lead,
            source_unit=primary_unit,
            has_annotations=record.annotation_count > 0,
            annotation_count=record.annotation_count,
            metadata={
                "adapterId": self.adapter_id,
                "format": self.format,
                "sourceUnit": primary_unit,
                "verification": "verified",
                "channelCount": len(record.header.signals),
                "importedChannels": len(record.imported),
                "recordDurationSec": record.header.record_duration,
                "recordStart": record.header.start_time,
                "timezoneKnown": False,
                "hasAnnotations": record.annotation_count > 0,
                "annotationCount": record.annotation_count,
            },
            warnings=warnings,
        )
        return finalize_parsed(parsed, parameters)


__all__ = ["EdfImportAdapter"]

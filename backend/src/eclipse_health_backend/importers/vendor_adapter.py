"""厂商波形适配器的公共实现（Samsung / Huawei / Apple）。

没有真实样本的厂商不猜字段：只识别公开导出里常见的 CSV 列名与 JSON 键，
找不到采样率/单位/导联时在 preview 标 ``requires``，由用户提交前补齐。
Apple Health 的单导联 I / mV 是公开规格，仅在缺省时才采用并给出 ``*_assumed`` 警告。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from .base import (
    TARGET_FS,
    Detection,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    detect_unit_in_text,
    finalize_parsed,
    normalize_lead_name,
    normalize_unit,
    unit_scale,
    warning,
)
from .errors import ImportApiError, invalid_file
from .tabular import Table, compact, load_text, numeric_column, parse_table

MAX_PREVIEW_SAMPLES = 2000
TEXT_SUFFIXES = {".csv", ".tsv", ".txt"}
JSON_SUFFIXES = {".json"}

FS_KEYS = {
    "samplingrate",
    "samplerate",
    "samplingfrequency",
    "samplefrequency",
    "fs",
    "frequency",
    "hz",
}
INTERVAL_KEYS = {
    "samplinginterval",
    "sampleinterval",
    "samplingperiod",
    "sampleperiod",
    "interval",
    "period",
    "dt",
}
UNIT_KEYS = {"unit", "units", "voltageunit", "valueunit", "amplitudeunit", "signalunit"}
LEAD_KEYS = {"lead", "leads", "leadname", "channel", "channelname", "electrode"}
SAMPLE_KEYS = {
    "samples",
    "sample",
    "ecg",
    "ecgdata",
    "ecgsamples",
    "wavedata",
    "wave",
    "waveform",
    "waveformdata",
    "values",
    "voltages",
    "voltage",
    "amplitudes",
    "points",
    "rawdata",
    "signal",
    "data",
}
TIME_KEYS = {
    "timestamp",
    "timestamps",
    "time",
    "times",
    "datetime",
    "date",
    "starttime",
    "starttimestamp",
    "recordedat",
    "startdate",
    "begin",
    "elapsed",
}
TIME_UNIT_RE = re.compile(r"(?:\(|\[|\b)(ms|msec|millisecond|milliseconds|us|µs|μs|microsecond|s|sec|seconds)(?:\)|\]|\b)", re.IGNORECASE)
SAMPLING_RATE_RE = re.compile(
    r"sampl\w*\s*(?:rate|frequency)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE
)
SAMPLING_INTERVAL_RE = re.compile(
    r"sampl\w*\s*(?:interval|period)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(ms|us|µs|μs|s)?",
    re.IGNORECASE,
)
UNIT_COMMENT_RE = re.compile(r"\bunit[s]?\b\s*[:=]\s*(mv|uv|µv|μv|v)\b", re.IGNORECASE)


@dataclass(frozen=True)
class VendorProfile:
    adapter_id: str
    format: str
    label: str
    brand: str
    name_tokens: tuple[str, ...]
    default_lead: str | None = None
    default_unit: str | None = None
    infer_voltage_unit: bool = False


@dataclass(slots=True)
class _Wave:
    values: np.ndarray
    fs: float | None = None
    unit: str | None = None
    lead: str | None = None
    start_time: str | None = None
    times: np.ndarray | None = None
    assumed_unit: bool = False
    assumed_lead: bool = False
    unit_annotated: bool = False
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class VendorData:
    path: Path
    wave: _Wave
    warnings: list[dict[str, Any]]


def _time_unit_hint(raw_header: str) -> float | None:
    """返回「1 秒等于多少个该列单位」。"""
    match = TIME_UNIT_RE.search(raw_header or "")
    if not match:
        return None
    token = match.group(1).lower()
    if token in {"ms", "msec", "millisecond", "milliseconds"}:
        return 1_000.0
    if token in {"us", "µs", "μs", "microsecond"}:
        return 1_000_000.0
    return 1.0


def _sampling_from_interval(value: float, raw_header: str) -> float | None:
    if value <= 0:
        return None
    hint = _time_unit_hint(raw_header)
    if hint is None:
        hint = 1_000.0 if value > 0.5 else 1.0
    return round(hint / value, 6)


def _sampling_from_times(values: np.ndarray, raw_header: str) -> tuple[float | None, str | None]:
    """从时间列/时间戳推导采样率；返回 (fs, ISO 起始时间)。"""
    if values.size < 2:
        return None, None
    diffs = np.diff(values)
    if not np.all(diffs > 0):
        return None, None
    median = float(np.median(diffs[: min(diffs.size, 2000)]))
    if median <= 0:
        return None, None
    hint = _time_unit_hint(raw_header)
    if hint is not None:
        return round(hint / median, 6), None
    seconds_rate = 1.0 / median
    milliseconds_rate = 1_000.0 / median
    if 1.0 <= milliseconds_rate <= 20_000.0 and (milliseconds_rate < seconds_rate or median > 0.5):
        return round(milliseconds_rate, 6), None
    return round(seconds_rate, 6), None


def _parse_time_values(
    tokens: list[str], raw_header: str
) -> tuple[float | None, str | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    numeric: list[float] = []
    for token in tokens:
        try:
            numeric.append(float(token))
        except ValueError:
            numeric = []
            break
    if numeric:
        values = np.asarray(numeric, dtype=np.float64)
        fs, start = _sampling_from_times(values, raw_header)
        if fs is None and np.unique(values).size > 1:
            warnings.append(
                warning("time_not_monotonic", "时间列不是严格递增，无法推算采样率", severity="warning")
            )
        return fs, start, warnings

    parsed: list[float] = []
    start_iso: str | None = None
    for token in tokens:
        try:
            moment = datetime.fromisoformat(token.strip())
        except ValueError:
            raise invalid_file(
                "时间列既不是数字也不是 ISO 时间",
                details={"value": token[:64]},
            ) from None
        if start_iso is None and moment.tzinfo is not None:
            start_iso = moment.isoformat()
        parsed.append(moment.timestamp())
    fs, _ = _sampling_from_times(np.asarray(parsed, dtype=np.float64), "")
    if fs is None and len(parsed) > 1:
        warnings.append(
            warning("time_not_monotonic", "时间戳不是严格递增，无法推算采样率", severity="warning")
        )
    return fs, start_iso, warnings


def _comments_sampling(comments: list[str]) -> tuple[float | None, float | None]:
    rate = None
    interval = None
    for comment in comments:
        match = SAMPLING_RATE_RE.search(comment)
        if match:
            value = float(match.group(1))
            if value > 0:
                rate = value
            continue
        match = SAMPLING_INTERVAL_RE.search(comment)
        if match:
            value = float(match.group(1))
            unit = (match.group(2) or "ms").lower()
            if unit in {"ms", "msec", "millisecond"}:
                interval = value / 1_000.0
            elif unit in {"us", "µs", "μs"}:
                interval = value / 1_000_000.0
            else:
                interval = value
    return rate, (1.0 / interval if interval else None)


def _comments_unit(comments: list[str]) -> str | None:
    for comment in comments:
        match = UNIT_COMMENT_RE.search(comment)
        if match:
            return normalize_unit(match.group(1))
    return None


def _normalize_vendor_lead(value: str) -> str:
    """``Lead I`` / ``lead_II`` 这类写法先去掉 ``Lead`` 前缀再归一。"""
    text = str(value).strip()
    prefix = re.match(r"^\s*lead[\s_\-:]*", text, re.IGNORECASE)
    if prefix:
        text = text[prefix.end() :].strip() or text
    return normalize_lead_name(text, 0)


def _is_time_token(token: str) -> bool:
    return token in TIME_KEYS or "time" in token or token in {"t", "ts", "sec", "seconds", "elapsed"}


def _is_voltage_token(token: str) -> bool:
    if token in UNIT_KEYS or token in {"lead", "leads", "leadname", "channel", "channelname"}:
        return False
    if token in FS_KEYS or token in INTERVAL_KEYS:
        return False
    return (
        "voltage" in token
        or "ecg" in token
        or "wave" in token
        or "amplitude" in token
        or "signal" in token
        or token in {"value", "values", "mv", "lead", "leadi", "leadii"}
        or (token.startswith("lead") and len(token) > 4)
    )


class VendorImportAdapter(ImportAdapter):
    profile: ClassVar[VendorProfile]

    def __init__(self) -> None:
        self.adapter_id = self.profile.adapter_id
        self.format = self.profile.format

    # ---------------------------------------------------------------- detect
    def _candidates(self, source: ImportSource) -> list[Path]:
        suffixes = TEXT_SUFFIXES | JSON_SUFFIXES

        def _files(root: Path) -> list[Path]:
            return sorted(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in suffixes
            )

        if source.extracted_dir is not None:
            return _files(source.extracted_dir)
        if source.path.is_dir():
            return _files(source.path)
        if source.path.suffix.lower() in suffixes:
            return [source.path]
        return []

    def _name_marked(self, path: Path, source: ImportSource) -> bool:
        name = (source.original_name if path == source.path and source.original_name else path.name)
        token = compact(name)
        return any(marker in token for marker in self.profile.name_tokens)

    @staticmethod
    def _read_head(path: Path, limit: int = 8192) -> str:
        try:
            with path.open("rb") as handle:
                raw = handle.read(limit)
        except OSError:
            return ""
        return raw.decode("latin-1", errors="replace")

    def _json_has_marker(self, path: Path) -> bool:
        try:
            text, _, _ = load_text(path)
            payload = json.loads(text)
        except (ImportApiError, ValueError):
            return False

        def walk(node: Any, depth: int) -> bool:
            if depth > 6:
                return False
            if isinstance(node, dict):
                for key, value in node.items():
                    token = compact(key)
                    if any(marker in token for marker in self.profile.name_tokens):
                        return True
                    if isinstance(value, str) and any(
                        marker in compact(value) for marker in self.profile.name_tokens
                    ):
                        return True
                    if walk(value, depth + 1):
                        return True
            elif isinstance(node, list):
                return any(walk(item, depth + 1) for item in node[:50])
            return False

        return walk(payload, 0)

    def _content_marked(self, path: Path) -> bool:
        if path.suffix.lower() in JSON_SUFFIXES:
            return self._json_has_marker(path)
        head = compact(self._read_head(path))
        return any(marker in head for marker in self.profile.name_tokens)

    def _marked(self, path: Path, source: ImportSource) -> tuple[bool, bool]:
        return self._name_marked(path, source), self._content_marked(path)

    def detect(self, source: ImportSource) -> Detection | None:
        best: Detection | None = None
        for path in self._candidates(source)[:20]:
            name_marked, content_marked = self._marked(path, source)
            if not (name_marked or content_marked):
                continue
            if name_marked and content_marked:
                score = 0.97
            elif content_marked:
                score = 0.94
            else:
                score = 0.93
            reason = "文件名与内容带厂商标识" if score == 0.97 else (
                "内容带厂商标识" if score == 0.94 else "文件名带厂商标识"
            )
            candidate = Detection(self.format, score, reason)
            if best is None or candidate.confidence > best.confidence:
                best = candidate
        return best

    def _pick_file(self, source: ImportSource) -> Path:
        candidates = self._candidates(source)
        if not candidates:
            raise invalid_file(f"未找到 {self.profile.label} 导出文件")
        if len(candidates) > 1:
            marked = [
                path
                for path in candidates
                if any(flag for flag in self._marked(path, source))
            ]
            if len(marked) == 1:
                return marked[0]
            raise invalid_file(
                "目录或压缩包里有多个可解析文件，请只保留一个",
                details={"candidates": [item.name for item in candidates]},
            )
        return candidates[0]

    # ------------------------------------------------------------- CSV parse
    @staticmethod
    def _find_columns(table: Table) -> dict[str, int | None]:
        assert table.header is not None
        tokens = [compact(name) for name in table.header]
        found: dict[str, int | None] = {
            "time": None,
            "voltage": None,
            "lead": None,
            "unit": None,
            "rate": None,
            "interval": None,
        }
        voltage_hits: list[int] = []
        for index, token in enumerate(tokens):
            if found["time"] is None and _is_time_token(token) and token not in INTERVAL_KEYS:
                found["time"] = index
            if token in LEAD_KEYS:
                found["lead"] = found["lead"] if found["lead"] is not None else index
            if token in UNIT_KEYS:
                found["unit"] = found["unit"] if found["unit"] is not None else index
            if token in FS_KEYS:
                found["rate"] = found["rate"] if found["rate"] is not None else index
            if token in INTERVAL_KEYS:
                found["interval"] = found["interval"] if found["interval"] is not None else index
            if _is_voltage_token(token) and index != found["time"]:
                voltage_hits.append(index)
        if voltage_hits:
            found["voltage"] = voltage_hits[0]
        return found

    def _read_csv(self, path: Path) -> _Wave:
        table = parse_table(path)
        if table.header is None:
            raise invalid_file(
                f"{self.profile.label} CSV 缺少表头，无法映射时间/电压列"
            )
        columns = self._find_columns(table)
        if columns["voltage"] is None:
            raise invalid_file(
                "未找到电压列",
                details={"headers": [name[:64] for name in table.header]},
            )
        voltage_col = int(columns["voltage"])
        values = np.asarray(numeric_column(table.rows, voltage_col)[0], dtype=np.float64)
        if values.size == 0:
            raise invalid_file("CSV 没有电压数据")

        wave = _Wave(values=values)
        warnings: list[dict[str, Any]] = list(table.warnings)
        if len([index for index in range(len(table.header)) if index != columns["time"] and _is_voltage_token(compact(table.header[index]))]) > 1:
            warnings.append(
                warning(
                    "multiple_voltage_columns",
                    "发现多个疑似电压列，已使用第一列",
                    severity="warning",
                )
            )

        raw_voltage_header = table.header[voltage_col]
        unit = detect_unit_in_text(raw_voltage_header)
        if unit is None and re.search(r"[\(\[]", raw_voltage_header):
            # 表头写了方括号单位但不在 mV/uV/nV/V 里（如 ADC），不要套默认单位。
            wave.unit_annotated = True
        if unit is None and columns["unit"] is not None:
            unit_values = {row[1][int(columns["unit"])].strip() for row in table.rows}
            unit_values.discard("")
            if len(unit_values) == 1:
                unit = normalize_unit(next(iter(unit_values)))
                if unit is None:
                    wave.unit_annotated = True
            elif len(unit_values) > 1:
                warnings.append(
                    warning("unit_inconsistent", "单位列存在多种取值，提交时需确认", severity="warning")
                )
        wave.unit = unit or _comments_unit(table.comments)
        if wave.unit is None and self.profile.infer_voltage_unit:
            wave.unit, inferred = self._infer_voltage_unit(values)
            if inferred:
                wave.assumed_unit = True
                warnings.append(
                    warning(
                        "unit_inferred",
                        f"按电压量级推断单位为 {wave.unit}（HealthKit 为 V，社区导出常为 mV）",
                        severity="warning",
                    )
                )
            elif wave.unit is None:
                wave.unit_annotated = True
                warnings.append(
                    warning(
                        "unit_ambiguous",
                        "电压量级既不像 V 也不像 mV，提交时需指定单位",
                        severity="warning",
                    )
                )

        if columns["lead"] is not None:
            lead_values = {row[1][int(columns["lead"])].strip() for row in table.rows}
            lead_values.discard("")
            if len(lead_values) == 1:
                wave.lead = _normalize_vendor_lead(next(iter(lead_values)))
        if wave.lead is None and "lead" in raw_voltage_header.lower():
            wave.lead = _normalize_vendor_lead(raw_voltage_header)

        if columns["rate"] is not None:
            rates, _ = numeric_column(table.rows, int(columns["rate"]))
            rate_values = [value for value in rates if value > 0]
            if rate_values:
                wave.fs = round(float(np.median(rate_values)), 6)
        if wave.fs is None and columns["interval"] is not None:
            intervals, _ = numeric_column(table.rows, int(columns["interval"]))
            positive = [value for value in intervals if value > 0]
            if positive:
                wave.fs = _sampling_from_interval(
                    float(np.median(positive)),
                    table.header[int(columns["interval"])],
                )

        comment_rate, comment_interval = _comments_sampling(table.comments)
        if wave.fs is None:
            wave.fs = comment_rate or comment_interval

        if columns["time"] is not None:
            tokens = [row[1][int(columns["time"])] for row in table.rows]
            fs, start, time_warnings = _parse_time_values(
                tokens, table.header[int(columns["time"])]
            )
            warnings.extend(time_warnings)
            if wave.fs is None:
                wave.fs = fs
            if wave.fs is not None and fs is not None and abs(wave.fs - fs) > 1e-6:
                warnings.append(
                    warning(
                        "sampling_rate_mismatch",
                        f"文件声明的采样率 {wave.fs:g} Hz 与时间列推算的 {fs:g} Hz 不一致，"
                        "已采用文件声明值",
                        severity="warning",
                    )
                )
            wave.start_time = start

        self._apply_defaults(wave, warnings)
        wave.warnings.extend(warnings)
        return wave

    @staticmethod
    def _infer_voltage_unit(values: np.ndarray) -> tuple[str | None, bool]:
        """HealthKit 以 V 存储；社区导出常写 mV。量级不像任何物理单位时不猜。"""
        if values.size == 0:
            return None, False
        median = float(np.median(np.abs(values)))
        if median < 0.02:
            return "V", True
        if 0.1 <= median <= 5.0:
            return "mV", True
        return None, False

    def _apply_defaults(self, wave: _Wave, warnings: list[dict[str, Any]]) -> None:
        if wave.unit is None and self.profile.default_unit and not wave.unit_annotated:
            wave.unit = self.profile.default_unit
            wave.assumed_unit = True
            warnings.append(
                warning(
                    "unit_assumed",
                    f"{self.profile.label} 导出未标注单位，按公开规格暂按 {wave.unit} 处理",
                    severity="warning",
                )
            )
        if wave.lead is None and self.profile.default_lead:
            wave.lead = self.profile.default_lead
            wave.assumed_lead = True
            warnings.append(
                warning(
                    "lead_assumed",
                    f"{self.profile.label} 导出未标注导联，按单导联 {wave.lead} 处理",
                    severity="warning",
                )
            )

    # ------------------------------------------------------------ JSON parse
    def _read_json(self, path: Path) -> _Wave:
        text, _, warnings = load_text(path)
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise invalid_file("JSON 无法解析", details={"reason": str(exc)[:200]}) from exc
        waves = self._json_waves(payload)
        unique: dict[tuple[Any, ...], _Wave] = {}
        for wave in waves:
            key = (
                int(wave.values.size),
                round(float(wave.values[0]), 6),
                round(float(wave.values[-1]), 6),
                round(float(np.sum(wave.values)), 6),
                wave.fs,
            )
            unique.setdefault(key, wave)
        if not unique:
            raise invalid_file("JSON 里没有找到数值波形数组")
        if len(unique) > 1:
            raise invalid_file(
                "JSON 里有多段 ECG 波形，批量导入暂不支持",
                details={"candidates": len(unique)},
            )
        wave = next(iter(unique.values()))
        wave.warnings.extend(warnings)
        self._apply_defaults(wave, wave.warnings)
        return wave

    def _json_waves(self, payload: Any) -> list[_Wave]:
        waves: list[_Wave] = []

        def relevant(node: dict[str, Any]) -> dict[str, Any]:
            found: dict[str, Any] = {}
            for key, value in node.items():
                token = compact(key)
                if token in FS_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
                    found["fs"] = float(value)
                elif token in INTERVAL_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
                    found["interval"] = (float(value), key)
                elif token in UNIT_KEYS and isinstance(value, str):
                    found["unit"] = value
                elif token in LEAD_KEYS and isinstance(value, str):
                    found["lead"] = value
                elif token in TIME_KEYS and isinstance(value, str):
                    found["start"] = value
            return found

        def add(values: list[Any], context: dict[str, Any], node: dict[str, Any]) -> bool:
            numeric = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            if len(numeric) != len(values) or len(numeric) < 2:
                return False
            wave = _Wave(values=np.asarray(numeric, dtype=np.float64))
            wave.fs = context.get("fs")
            if wave.fs is None and context.get("interval"):
                interval, raw_key = context["interval"]
                wave.fs = _sampling_from_interval(interval, raw_key)
            raw_unit = context.get("unit")
            wave.unit = normalize_unit(raw_unit) if raw_unit else None
            if raw_unit and wave.unit is None:
                wave.unit_annotated = True
                wave.warnings.append(
                    warning(
                        "unsupported_unit",
                        f"JSON 单位 {str(raw_unit)[:32]} 无法识别，提交时需确认",
                        severity="warning",
                    )
                )
            if context.get("lead"):
                wave.lead = _normalize_vendor_lead(context["lead"])
            wave.start_time = context.get("start")

            time_list = None
            for key, value in node.items():
                token = compact(key)
                if token in TIME_KEYS and isinstance(value, list) and len(value) == len(values):
                    time_list = value
            if wave.fs is None and time_list:
                try:
                    times = np.asarray([float(value) for value in time_list], dtype=np.float64)
                except (TypeError, ValueError):
                    times = None
                if times is not None:
                    wave.fs, iso = _sampling_from_times(times, "")
                    wave.start_time = wave.start_time or iso
                    wave.times = times
            waves.append(wave)
            return True

        def row_style(items: list[Any]) -> _Wave | None:
            if not items or not all(isinstance(item, dict) for item in items):
                return None
            voltage_key = time_key = None
            for key in items[0]:
                token = compact(key)
                if time_key is None and _is_time_token(token):
                    time_key = key
                if voltage_key is None and _is_voltage_token(token):
                    voltage_key = key
            if voltage_key is None:
                return None
            try:
                values = np.asarray([float(item[voltage_key]) for item in items], dtype=np.float64)
            except (KeyError, TypeError, ValueError):
                return None
            wave = _Wave(values=values)
            if time_key is not None:
                tokens = [str(item.get(time_key, "")) for item in items]
                fs, start, time_warnings = _parse_time_values(tokens, time_key)
                wave.fs = fs
                wave.start_time = start
                wave.warnings.extend(time_warnings)
            for key in items[0]:
                token = compact(key)
                if wave.unit is None and token in UNIT_KEYS:
                    wave.unit = normalize_unit(str(items[0][key]))
                if wave.lead is None and token in LEAD_KEYS:
                    wave.lead = _normalize_vendor_lead(str(items[0][key]))
            return wave

        def walk(node: Any, context: dict[str, Any], depth: int) -> None:
            if depth > 8:
                return
            if isinstance(node, dict):
                local = dict(context)
                local.update(relevant(node))
                sample_key = None
                for key, value in node.items():
                    if (
                        compact(key) in SAMPLE_KEYS
                        and isinstance(value, list)
                        and value
                        and add(value, local, node)
                    ):
                        sample_key = key
                        break
                for key, value in node.items():
                    if key == sample_key:
                        continue
                    walk(value, local, depth + 1)
            elif isinstance(node, list):
                row = row_style(node)
                if row is not None:
                    waves.append(row)
                    return
                for item in node[:500]:
                    walk(item, context, depth + 1)

        walk(payload, {}, 0)
        return waves

    # ------------------------------------------------------------- analysis
    def _analyze(self, source: ImportSource) -> VendorData:
        path = self._pick_file(source)
        wave = self._read_json(path) if path.suffix.lower() in JSON_SUFFIXES else self._read_csv(path)
        warnings = list(wave.warnings)
        warnings.append(
            warning(
                "experimental_format",
                f"{self.profile.label} 适配器未用真实样本验证，字段按公开资料映射，"
                "请核对采样率、单位与导联",
                severity="warning",
            )
        )
        if wave.fs is not None and abs(wave.fs - TARGET_FS) > 1e-6:
            warnings.append(
                warning(
                    "non_target_sampling_rate",
                    f"采样率 {wave.fs:g} Hz，分析引擎以 360 Hz 为基准",
                    severity="warning",
                )
            )
        if wave.fs is None:
            warnings.append(
                warning("sampling_rate_unknown", "未能确定采样率，提交时需指定", severity="warning")
            )
        if wave.unit is None:
            warnings.append(
                warning("unit_unknown", "未能确定电压单位，提交时需指定", severity="warning")
            )
        if wave.lead is None:
            warnings.append(
                warning("lead_unknown", "未能确定导联，提交时需指定", severity="warning")
            )
        return VendorData(path=path, wave=wave, warnings=warnings)

    # --------------------------------------------------------------- preview
    def preview(self, source: ImportSource) -> PreviewData:
        data = self._analyze(source)
        wave = data.wave
        scale = unit_scale(wave.unit) if wave.unit else 1.0
        samples = wave.values[:MAX_PREVIEW_SAMPLES] * (scale or 1.0)
        return PreviewData(
            sampling_rate=wave.fs,
            leads=[wave.lead] if wave.lead else [],
            duration_sec=(wave.values.size / wave.fs) if wave.fs else None,
            unit="mV",
            requires_sampling_rate=wave.fs is None,
            requires_lead=wave.lead is None,
            requires_unit=wave.unit is None,
            warnings=data.warnings,
            n_samples=int(wave.values.size),
            samples=[float(value) for value in samples],
        )

    # ----------------------------------------------------------------- parse
    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        data = self._analyze(source)
        wave = data.wave

        sampling_rate = parameters.sampling_rate or wave.fs
        if sampling_rate is None:
            raise ImportApiError(
                "缺少采样率，请用 parameters.samplingRate 指定",
                code="sampling_rate_required",
            )
        unit = normalize_unit(parameters.unit) if parameters.unit else wave.unit
        if parameters.unit and unit is None:
            raise ImportApiError(
                "无法识别的单位参数（可用 mV/uV/V）",
                code="invalid_parameter",
                details={"unit": parameters.unit},
            )
        if unit is None:
            raise ImportApiError(
                "缺少电压单位，请用 parameters.unit 指定",
                code="unit_required",
            )
        lead = normalize_lead_name(parameters.lead, 0) if parameters.lead else wave.lead
        if lead is None:
            raise ImportApiError(
                "无法确定导联，请用 parameters.lead 指定",
                code="lead_required",
            )

        scale = unit_scale(unit) or 1.0
        samples = wave.values.astype(np.float64) * scale
        parsed = ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=float(sampling_rate),
            duration_sec=samples.size / float(sampling_rate),
            leads=[
                ParsedLead(
                    lead=lead,
                    samples=samples,
                    # 厂商导出没有 ADC 数字量，沿用 CSV 的 gain=200 映射。
                    digital=samples * 200.0,
                    gain=200.0,
                )
            ],
            primary_lead=lead,
            source_unit=unit,
            metadata={
                "adapterId": self.adapter_id,
                "format": self.format,
                "sourceUnit": unit,
                "vendor": self.profile.brand,
                "verification": "experimental",
                "startTime": wave.start_time,
                "hasAnnotations": False,
                "annotationCount": 0,
            },
            warnings=list(data.warnings),
        )
        return finalize_parsed(parsed, parameters)


__all__ = ["VendorData", "VendorImportAdapter", "VendorProfile"]

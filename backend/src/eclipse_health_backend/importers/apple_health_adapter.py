"""Apple 健康导出（``export.zip`` / ``export.xml`` + ``electrocardiograms/*.csv``）。

把 Apple Health 的官方导出直接变成 eclipse health 记录：
- 步数 / 心率 / 睡眠 / 体重 / 血压（Correlation）；
- 每段 ECG CSV → 一条单导联 I 记录 + 信号（伏特换算为 mV）。

XML 用 ``iterparse`` 流式读取，不把整个 ``export.xml`` 读进内存；
超过 ``limits.HEALTH_MAX_RECORDS`` 直接报错。导入不做诊断推断。
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from . import limits
from .base import (
    Detection,
    HealthRecordDraft,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    warning,
)
from .errors import invalid_file
from .tabular import compact

EXPORT_XML = "export.xml"
ECG_DIR = "electrocardiograms"
ECG_TYPE = "HKDataTypeIdentifierElectrocardiogram"
SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
BP_CORRELATION = "HKCorrelationTypeIdentifierBloodPressure"
BP_SYSTOLIC = "HKQuantityTypeIdentifierBloodPressureSystolic"
BP_DIASTOLIC = "HKQuantityTypeIdentifierBloodPressureDiastolic"

DEFAULT_ECG_FS = 512.0
MAX_PREVIEW_SAMPLES = 2000
ECG_META_MATCH_SECONDS = 600.0

# Apple type -> (kind, UCUM 单位)
QUANTITY_TYPES: dict[str, tuple[str, str]] = {
    "HKQuantityTypeIdentifierStepCount": ("steps", "count"),
    "HKQuantityTypeIdentifierHeartRate": ("heart-rate", "count/min"),
    "HKQuantityTypeIdentifierBodyMass": ("body-mass", "kg"),
}

KIND_RECORD_TYPES = {
    "steps": "org.eclipsehealth.health.steps",
    "heart-rate": "org.eclipsehealth.health.heart-rate",
    "sleep": "org.eclipsehealth.health.sleep",
    "body-mass": "org.eclipsehealth.health.body-mass",
    "blood-pressure": "org.eclipsehealth.health.blood-pressure",
}

# 预览/API 的 recordCounts 键。
COUNT_KEYS = {
    "steps": "steps",
    "heart-rate": "heartRate",
    "sleep": "sleep",
    "body-mass": "bodyMass",
    "blood-pressure": "bloodPressure",
    "ecg": "ecg",
}

SLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisInBed": "in-bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "asleep-core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "asleep-deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "asleep-rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAwake": "awake",
}

_DATE_IN_TEXT = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*[+-]\d{2}:?\d{2}|Z)?"
)
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S %z",
    "%Y-%m-%d %H:%M:%S.%f %z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_apple_date(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC)
    return None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _fingerprint(*parts: Any) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _external_id(attrs: dict[str, str], *parts: Any) -> str:
    for key in ("uuid", "UUID", "HKObjectUUID"):
        value = attrs.get(key)
        if value:
            return f"apple:{value}"
    return f"apple:{_fingerprint(*parts)}"


def _number(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _tidy(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(value, 6)


def _source_app(attrs: dict[str, str]) -> str | None:
    name = (attrs.get("sourceName") or "").strip()
    return name[:64] or None


@dataclass(slots=True)
class _ScanResult:
    health: list[HealthRecordDraft] = field(default_factory=list)
    ecg_meta: list[dict[str, Any]] = field(default_factory=list)
    ignored: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    warnings: list[dict[str, Any]] = field(default_factory=list)


class AppleHealthAdapter(ImportAdapter):
    """Apple Health 导出包（不是单段 ECG CSV；后者由 ``apple_adapter`` 处理）。"""

    adapter_id = "org.eclipsehealth.apple-health"
    adapter_version = "1.0.0"
    format = "apple-health"

    # ---------------------------------------------------------------- detect
    def detect(self, source: ImportSource) -> Detection | None:
        xml_path = self._find_export_xml(source, missing_ok=True)
        if xml_path is not None:
            return Detection(self.format, 0.99, "找到 Apple export.xml")
        if source.encrypted:
            return None
        if self._looks_like_broken_apple_export(source):
            return Detection(self.format, 0.96, "像 Apple 健康导出但缺少 export.xml")
        return None

    @staticmethod
    def _looks_like_health_xml(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                head = handle.read(8192)
        except OSError:
            return False
        return b"<HealthData" in head

    def _find_export_xml(self, source: ImportSource, *, missing_ok: bool) -> Path | None:
        if source.path.is_file() and source.path.suffix.lower() == ".xml":
            if source.path.name.lower() == EXPORT_XML or self._looks_like_health_xml(source.path):
                return source.path
            return None
        root = source.extracted_dir if source.extracted_dir is not None else (
            source.path if source.path.is_dir() else None
        )
        if root is None:
            return None
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.name.lower() == EXPORT_XML:
                return candidate
        return None

    @staticmethod
    def _looks_like_broken_apple_export(source: ImportSource) -> bool:
        root = source.extracted_dir if source.extracted_dir is not None else (
            source.path if source.path.is_dir() else None
        )
        if root is None:
            return False
        for candidate in root.rglob("*"):
            if candidate.is_dir() and candidate.name.lower() == ECG_DIR:
                return True
            if candidate.is_dir() and "apple_health_export" in candidate.name.lower():
                return True
        return False

    # ---------------------------------------------------------------- bundle
    def _build(self, source: ImportSource) -> ParsedImport:
        xml_path = self._find_export_xml(source, missing_ok=False)
        if xml_path is None:
            raise invalid_file(
                "压缩包里没有 export.xml，请确认选择的是 Apple 健康「导出所有健康数据」生成的 export.zip",
                code="apple_export_missing",
            )

        scan = _ScanResult()
        self._scan_xml(xml_path, scan)
        counts: dict[str, int] = {}
        for draft in scan.health:
            key = COUNT_KEYS.get(draft.kind, draft.kind)
            counts[key] = counts.get(key, 0) + 1

        ecg_paths = self._ecg_files(source)
        if len(ecg_paths) > limits.HEALTH_MAX_ECG_FILES:
            raise invalid_file(
                f"心电图文件超过 {limits.HEALTH_MAX_ECG_FILES} 个上限",
                code="import_too_many_records",
                details={
                    "ecgFiles": len(ecg_paths),
                    "limit": limits.HEALTH_MAX_ECG_FILES,
                },
            )

        ecg_records: list[ParsedImport] = []
        for index, path in enumerate(ecg_paths):
            ecg_records.append(self._ecg_record(path, scan.ecg_meta, index, scan.warnings))
        if ecg_records:
            counts["ecg"] = len(ecg_records)

        total = len(scan.health) + len(ecg_records)
        if total == 0:
            raise invalid_file(
                "Apple 导出里没有可导入的步数/心率/睡眠/体重/血压/心电图记录",
                code="apple_export_empty",
            )
        if total > limits.HEALTH_MAX_RECORDS:
            raise invalid_file(
                f"记录数超过 {limits.HEALTH_MAX_RECORDS} 条上限，请缩小导出时间范围",
                code="import_too_many_records",
                details={"records": total, "limit": limits.HEALTH_MAX_RECORDS},
            )

        warnings = list(scan.warnings)
        if total > limits.HEALTH_LARGE_RECORDS:
            warnings.append(
                warning(
                    "large_import",
                    f"本次将导入 {total} 条记录，提交可能需要几分钟",
                    severity="warning",
                )
            )
        if scan.ignored:
            top = ", ".join(
                f"{name}×{count}" for name, count in scan.ignored.most_common(8)
            )
            warnings.append(
                warning(
                    "apple_ignored_types",
                    f"已跳过未映射的数据类型：{top}",
                    severity="info",
                )
            )
        if scan.skipped:
            total_skipped = sum(scan.skipped.values())
            warnings.append(
                warning(
                    "apple_skipped_records",
                    f"{total_skipped} 条记录因单位/数值/时间缺失被跳过",
                    severity="warning",
                )
            )
        warnings.append(
            warning(
                "apple_health_imported",
                f"Apple 健康导出：{len(scan.health)} 条健康记录、{len(ecg_records)} 段心电图",
                severity="info",
            )
        )

        first = ecg_records[0] if ecg_records else None
        return ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=first.sampling_rate if first else 0.0,
            duration_sec=first.duration_sec if first else 0.0,
            leads=[],
            primary_lead="",
            metadata={"importSource": "apple-health", "format": self.format},
            warnings=warnings,
            health_records=scan.health,
            ecg_records=ecg_records,
            record_counts=counts,
            total_records=total,
            import_source="apple-health",
        )

    # --------------------------------------------------------------- XML scan
    def _scan_xml(self, path: Path, scan: _ScanResult) -> None:
        current: dict[str, Any] | None = None
        root: ET.Element | None = None
        depth = 0
        try:
            context = ET.iterparse(str(path), events=("start", "end"))
            for event, elem in context:
                tag = _local(elem.tag)
                if event == "start":
                    depth += 1
                    if tag == "HealthData":
                        root = elem
                    elif tag == "Correlation":
                        current = {
                            "attrs": dict(elem.attrib),
                            "records": [],
                        }
                    continue

                if tag == "Record":
                    attrs = dict(elem.attrib)
                    if current is not None:
                        current["records"].append(attrs)
                    else:
                        self._record_draft(attrs, scan)
                elif tag == "Correlation":
                    if current is not None:
                        self._correlation_draft(current, scan)
                    current = None

                depth -= 1
                if depth == 1 and root is not None:
                    root.clear()
                if len(scan.health) > limits.HEALTH_MAX_RECORDS:
                    raise invalid_file(
                        f"记录数超过 {limits.HEALTH_MAX_RECORDS} 条上限，请缩小导出时间范围",
                        code="import_too_many_records",
                        details={"limit": limits.HEALTH_MAX_RECORDS},
                    )
        except ET.ParseError as exc:
            raise invalid_file(
                "export.xml 不是有效的 XML，可能未完整解压",
                code="invalid_apple_export",
                details={"reason": str(exc)[:200]},
            ) from exc

    def _record_draft(self, attrs: dict[str, str], scan: _ScanResult) -> None:
        type_ = attrs.get("type", "")
        if type_ == ECG_TYPE:
            start = parse_apple_date(attrs.get("startDate"))
            if start is not None:
                scan.ecg_meta.append(
                    {"start": start, "source": _source_app(attrs), "uuid": attrs.get("uuid")}
                )
            return
        if type_ == SLEEP_TYPE:
            draft = self._sleep_draft(attrs, scan)
        elif type_ in QUANTITY_TYPES:
            draft = self._quantity_draft(attrs, scan)
        else:
            scan.ignored[type_ or "unknown"] += 1
            return
        if draft is not None:
            scan.health.append(draft)

    def _quantity_draft(
        self, attrs: dict[str, str], scan: _ScanResult
    ) -> HealthRecordDraft | None:
        kind, canonical_unit = QUANTITY_TYPES[attrs.get("type", "")]
        start = parse_apple_date(attrs.get("startDate"))
        end = parse_apple_date(attrs.get("endDate")) or start
        value = _number(attrs.get("value"))
        if start is None or value is None:
            scan.skipped["invalid_value"] += 1
            return None
        converted = _convert_quantity(kind, value, attrs.get("unit", ""))
        if converted is None:
            scan.skipped["unsupported_unit"] += 1
            return None
        value, unit = converted
        source_app = _source_app(attrs)
        return HealthRecordDraft(
            record_type=KIND_RECORD_TYPES[kind],
            kind=kind,
            captured_at=start,
            external_id=_external_id(
                attrs, attrs.get("type"), attrs.get("startDate"), attrs.get("endDate"),
                attrs.get("value"), attrs.get("unit"), attrs.get("sourceName"),
            ),
            unit=unit or canonical_unit,
            source_app=source_app,
            duration_sec=max(0.0, (end - start).total_seconds()) if end else None,
            payload={
                "value": _tidy(value),
                "unit": unit or canonical_unit,
                "startAt": _iso(start),
                "endAt": _iso(end),
                **({"sourceApp": source_app} if source_app else {}),
            },
        )

    def _sleep_draft(
        self, attrs: dict[str, str], scan: _ScanResult
    ) -> HealthRecordDraft | None:
        start = parse_apple_date(attrs.get("startDate"))
        end = parse_apple_date(attrs.get("endDate")) or start
        raw = attrs.get("value", "")
        if start is None:
            scan.skipped["invalid_value"] += 1
            return None
        category = SLEEP_VALUES.get(raw, raw.removeprefix("HKCategoryValueSleepAnalysis").lower())
        if not category:
            category = "unknown"
        source_app = _source_app(attrs)
        return HealthRecordDraft(
            record_type=KIND_RECORD_TYPES["sleep"],
            kind="sleep",
            captured_at=start,
            external_id=_external_id(
                attrs, attrs.get("type"), attrs.get("startDate"), attrs.get("endDate"),
                raw, attrs.get("sourceName"),
            ),
            unit="1",
            source_app=source_app,
            duration_sec=max(0.0, (end - start).total_seconds()) if end else None,
            payload={
                "value": category,
                "unit": "1",
                "startAt": _iso(start),
                "endAt": _iso(end),
                **({"sourceApp": source_app} if source_app else {}),
            },
            metadata={"sleepCategory": category},
        )

    def _correlation_draft(
        self, correlation: dict[str, Any], scan: _ScanResult
    ) -> None:
        attrs = correlation["attrs"]
        if attrs.get("type") != BP_CORRELATION:
            scan.ignored[attrs.get("type", "unknown")] += 1
            return
        systolic = diastolic = None
        pressure_unit = ""
        for record in correlation["records"]:
            if record.get("type") == BP_SYSTOLIC:
                systolic = _number(record.get("value"))
                pressure_unit = pressure_unit or str(record.get("unit") or "")
            elif record.get("type") == BP_DIASTOLIC:
                diastolic = _number(record.get("value"))
                pressure_unit = pressure_unit or str(record.get("unit") or "")
        start = parse_apple_date(attrs.get("startDate"))
        end = parse_apple_date(attrs.get("endDate")) or start
        if systolic is None or diastolic is None or start is None:
            scan.skipped["invalid_blood_pressure"] += 1
            return
        unit = (pressure_unit or attrs.get("unit") or "mmHg").strip().lower()
        if unit in {"mmhg", "mm[hg]", "mm hg"}:
            scale = 1.0
        elif unit == "kpa":
            scale = 7.50062
        else:
            scan.skipped["unsupported_unit"] += 1
            return
        source_app = _source_app(attrs)
        scan.health.append(
            HealthRecordDraft(
                record_type=KIND_RECORD_TYPES["blood-pressure"],
                kind="blood-pressure",
                captured_at=start,
                external_id=_external_id(
                    attrs, attrs.get("type"), attrs.get("startDate"), attrs.get("endDate"),
                    systolic, diastolic, attrs.get("sourceName"),
                ),
                unit="mm[Hg]",
                source_app=source_app,
                duration_sec=max(0.0, (end - start).total_seconds()) if end else None,
                payload={
                    "value": {
                        "systolic": _tidy(systolic * scale),
                        "diastolic": _tidy(diastolic * scale),
                    },
                    "unit": "mm[Hg]",
                    "startAt": _iso(start),
                    "endAt": _iso(end),
                    **({"sourceApp": source_app} if source_app else {}),
                },
            )
        )

    # ------------------------------------------------------------- ECG files
    @staticmethod
    def _ecg_files(source: ImportSource) -> list[Path]:
        root = source.extracted_dir if source.extracted_dir is not None else (
            source.path if source.path.is_dir() else None
        )
        if root is None:
            return []
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".csv"
        ]
        preferred = [
            path for path in files if any(part.lower() == ECG_DIR for part in path.parts)
        ]
        selected = preferred or files
        return sorted(selected)

    def _ecg_record(
        self,
        path: Path,
        meta: list[dict[str, Any]],
        index: int,
        bundle_warnings: list[dict[str, Any]],
    ) -> ParsedImport:
        samples, fs, recorded_at, file_warnings = _parse_ecg_csv(path, index)
        matched = _match_ecg_meta(recorded_at, meta)
        source_app = matched.get("source") if matched else None
        captured_at = recorded_at or (matched.get("start") if matched else None)
        if fs is None:
            fs = DEFAULT_ECG_FS
            bundle_warnings.append(
                warning(
                    "apple_ecg_default_sampling_rate",
                    "心电图 CSV 的时间列无法推算采样率，按 Apple 常用 512 Hz 处理",
                    severity="warning",
                )
            )
        external_id = f"apple-ecg:{hashlib.sha256(path.read_bytes()).hexdigest()[:32]}"
        return ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=float(fs),
            duration_sec=samples.size / float(fs),
            leads=[
                ParsedLead(
                    lead="I",
                    samples=samples,
                    digital=samples * 200.0,
                    gain=200.0,
                )
            ],
            primary_lead="I",
            source_unit="V",
            metadata={
                "importSource": "apple-health",
                "externalId": external_id,
                "sourceApp": source_app,
                "sourceUnit": "V",
                "startTime": _iso(captured_at),
                "verification": "apple-health-export",
            },
            warnings=list(file_warnings),
            captured_at=captured_at,
        )

    # --------------------------------------------------------------- adapters
    def preview(self, source: ImportSource) -> PreviewData:
        parsed = self._build(source)
        first = parsed.ecg_records[0] if parsed.ecg_records else None
        samples: list[float] = []
        if first and first.leads:
            samples = [
                float(value) for value in first.leads[0].samples[:MAX_PREVIEW_SAMPLES]
            ]
        return PreviewData(
            sampling_rate=first.sampling_rate if first else None,
            leads=["I"] if first else [],
            duration_sec=first.duration_sec if first else None,
            unit="mV",
            requires_sampling_rate=False,
            requires_lead=False,
            requires_unit=False,
            warnings=list(parsed.warnings),
            n_samples=int(first.leads[0].samples.size) if first and first.leads else 0,
            samples=samples,
            record_counts=dict(parsed.record_counts),
            total_records=parsed.total_records,
        )

    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        # 健康数据包按文件自身的时间戳入库，不使用波形校正参数。
        return self._build(source)


def _convert_quantity(
    kind: str, value: float, raw_unit: str
) -> tuple[float, str] | None:
    unit = (raw_unit or "").strip().lower()
    if kind == "steps":
        if unit in {"", "count", "counts", "step", "steps"}:
            return value, "count"
        return None
    if kind == "heart-rate":
        if unit in {"", "count/min", "1/min", "/min", "bpm"}:
            return value, "count/min"
        if unit in {"count/s", "1/s", "/s"}:
            return value * 60.0, "count/min"
        return None
    if kind == "body-mass":
        if unit in {"", "kg", "kilogram", "kilograms"}:
            return value, "kg"
        if unit in {"lb", "lbs", "pound", "pounds"}:
            return value * 0.45359237, "kg"
        if unit in {"g", "gram", "grams"}:
            return value / 1000.0, "kg"
        return None
    return None


def _parse_ecg_csv(
    path: Path, index: int
) -> tuple[np.ndarray, float | None, datetime | None, list[dict[str, Any]]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise invalid_file(
            "无法读取心电图 CSV",
            code="invalid_ecg_csv",
            details={"index": index + 1},
        ) from exc
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header: tuple[int, int, int] | None = None
    for line_index, line in enumerate(lines[:50]):
        cells = [cell.strip().strip('"') for cell in line.split(",")]
        tokens = [compact(cell) for cell in cells]
        time_index = next(
            (i for i, token in enumerate(tokens) if token in {"time", "timestamp", "t", "seconds"}),
            None,
        )
        voltage_index = next(
            (
                i
                for i, token in enumerate(tokens)
                if token in {"voltage", "mv", "value", "ecg", "voltagev", "voltagemv"}
                or "voltage" in token
            ),
            None,
        )
        if time_index is not None and voltage_index is not None:
            header = (line_index, time_index, voltage_index)
            break
    if header is None:
        raise invalid_file(
            "心电图 CSV 缺少 time/voltage 表头",
            code="invalid_ecg_csv",
            details={"index": index + 1},
        )

    header_index, time_index, voltage_index = header
    recorded_at = None
    for line in lines[:header_index]:
        match = _DATE_IN_TEXT.search(line)
        if match:
            recorded_at = parse_apple_date(match.group(0))
            if recorded_at is not None:
                break

    times: list[float] = []
    values: list[float] = []
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        cells = [cell.strip().strip('"') for cell in line.split(",")]
        if max(time_index, voltage_index) >= len(cells):
            continue
        try:
            times.append(float(cells[time_index]))
            values.append(float(cells[voltage_index]))
        except ValueError:
            continue
    if len(values) < 2:
        raise invalid_file(
            "心电图 CSV 没有可用的 time/voltage 数据",
            code="invalid_ecg_csv",
            details={"index": index + 1},
        )

    time_array = np.asarray(times, dtype=np.float64)
    samples = np.asarray(values, dtype=np.float64) * 1000.0
    warnings: list[dict[str, Any]] = [
        warning(
            "unit_converted",
            "Apple 心电图以伏特存储，已换算为 mV",
            severity="info",
        )
    ]
    fs: float | None = None
    diffs = np.diff(time_array)
    if diffs.size and np.all(diffs > 0):
        median = float(np.median(diffs))
        if median > 0:
            candidate = 1.0 / median
            if 1.0 <= candidate <= 100_000.0:
                fs = round(candidate, 6)
    if fs is None:
        warnings.append(
            warning(
                "time_not_monotonic",
                "心电图时间列无法推算采样率，将使用 512 Hz",
                severity="warning",
            )
        )
    return samples, fs, recorded_at, warnings


def _match_ecg_meta(
    recorded_at: datetime | None, meta: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if recorded_at is None or not meta:
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for item in meta:
        start = item.get("start")
        if start is None:
            continue
        distance = abs((start - recorded_at).total_seconds())
        if distance > ECG_META_MATCH_SECONDS:
            continue
        if best is None or distance < best[0]:
            best = (distance, item)
    return best[1] if best else None


__all__ = ["AppleHealthAdapter", "parse_apple_date"]

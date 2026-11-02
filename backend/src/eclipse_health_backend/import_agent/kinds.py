"""健康记录 kind 的校验与规范化（docs/HEALTH_RECORD_KINDS.md 的事实源）。

Agent 产出的候选只在这里变成可信结构：单位、范围、证据、时间、ECG 波形引用
全部由服务端重新校验，不信任模型输出的形状。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from ..domain.ids import uuid7
from .errors import RecordValidationError

HEALTH_PREFIX = "org.eclipsehealth.health."
ECG_RECORD_TYPE = "org.eclipsehealth.ecg"
ADAPTER_VERSION = "import-agent/1.0.0"

MAX_VALUE_DECIMALS = 6
MAX_TEXT = 2000

ALLOWED_KEYS = {
    "kind",
    "value",
    "unit",
    "startAt",
    "endAt",
    "source",
    "evidence",
    "confidence",
    "waveform",
    "tags",
    "notes",
}

SLEEP_STAGES = {
    "in-bed",
    "awake",
    "asleep",
    "asleep-core",
    "asleep-deep",
    "asleep-rem",
    "unknown",
}

HRV_UNIT_BY_METRIC = {
    "rmssd": "ms",
    "sdnn": "ms",
    "pnn50": "%",
    "lf": "ms2",
    "hf": "ms2",
    "lf-hf-ratio": "1",
}
HRV_UNITS = {"ms", "%", "ms2", "1"}

BODY_METRIC_RANGES: dict[str, tuple[float, float]] = {
    "weightKg": (1.0, 500.0),
    "bodyFatPct": (1.0, 70.0),
    "bmi": (5.0, 80.0),
    "muscleMassKg": (1.0, 200.0),
    "waterPct": (1.0, 80.0),
    "boneMassKg": (0.1, 20.0),
    "visceralFat": (1.0, 60.0),
    "basalMetabolicRate": (500.0, 5000.0),
}

# 输入写法 -> 规范单位。键统一转小写后查表。
UNIT_ALIASES: dict[str, str] = {
    "bpm": "count/min",
    "1/min": "count/min",
    "/min": "count/min",
    "count/min": "count/min",
    "counts/min": "count/min",
    "count": "count",
    "counts": "count",
    "step": "count",
    "steps": "count",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "mmhg": "mm[Hg]",
    "mm[hg]": "mm[Hg]",
    "mm hg": "mm[Hg]",
    "kpa": "kPa",
    "%": "%",
    "percent": "%",
    "cel": "Cel",
    "°c": "Cel",
    "c": "Cel",
    "celsius": "Cel",
    "°f": "°F",
    "f": "°F",
    "fahrenheit": "°F",
    "mg/dl": "mg/dL",
    "mgdl": "mg/dL",
    "mmol/l": "mmol/L",
    "ms": "ms",
    "millisecond": "ms",
    "milliseconds": "ms",
    "ms2": "ms2",
    "ms²": "ms2",
    "mv": "mV",
    "uv": "uV",
    "µv": "uV",
    "μv": "uV",
    "v": "V",
    "1": "1",
}

SOURCE_KINDS = {"app", "device", "manual", "unknown"}


@dataclass(frozen=True, slots=True)
class KindSpec:
    kind: str
    units: tuple[str, ...]
    end_required: bool = False

    @property
    def record_type(self) -> str:
        if self.kind == "ecg":
            return ECG_RECORD_TYPE
        return f"{HEALTH_PREFIX}{self.kind}"


KIND_SPECS: dict[str, KindSpec] = {
    "steps": KindSpec("steps", ("count",)),
    "heart-rate": KindSpec("heart-rate", ("count/min",)),
    "resting-heart-rate": KindSpec("resting-heart-rate", ("count/min",)),
    "sleep": KindSpec("sleep", ("1",), end_required=True),
    "body-mass": KindSpec("body-mass", ("kg",)),
    "blood-pressure": KindSpec("blood-pressure", ("mm[Hg]",)),
    "spo2": KindSpec("spo2", ("%",)),
    "stress": KindSpec("stress", ("1",)),
    "workout": KindSpec("workout", ("1",), end_required=True),
    "respiratory-rate": KindSpec("respiratory-rate", ("count/min",)),
    "body-temperature": KindSpec("body-temperature", ("Cel",)),
    "blood-glucose": KindSpec("blood-glucose", ("mg/dL", "mmol/L")),
    "hrv": KindSpec("hrv", ("ms", "%", "ms2", "1")),
    "ecg": KindSpec("ecg", ("mV",)),
    "body": KindSpec("body", ("1",)),
}

KIND_NAMES: tuple[str, ...] = tuple(KIND_SPECS)


# --------------------------------------------------------------------------- #
# 基础校验
# --------------------------------------------------------------------------- #


def _fail(message: str, *, code: str = "invalid_record", details: Any = None) -> None:
    raise RecordValidationError(message, code=code, details=details)


def _text(
    value: Any,
    field: str,
    *,
    max_length: int,
    required: bool = True,
    allow_empty: bool = False,
) -> str | None:
    if value is None:
        if required:
            _fail(f"{field} is required", details={"field": field})
        return None
    if not isinstance(value, str):
        _fail(f"{field} must be a string", details={"field": field, "type": type(value).__name__})
    cleaned = value.strip()
    if not cleaned and not allow_empty:
        _fail(f"{field} must not be empty", details={"field": field})
    if len(cleaned) > max_length:
        _fail(
            f"{field} exceeds {max_length} characters",
            details={"field": field, "length": len(cleaned), "limit": max_length},
        )
    return cleaned


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field} must be a number", details={"field": field, "type": type(value).__name__})
    number = float(value)
    if not math.isfinite(number):
        _fail(f"{field} must be finite", details={"field": field})
    if minimum is not None and number < minimum:
        _fail(
            f"{field} must be >= {minimum}",
            details={"field": field, "value": number, "minimum": minimum},
        )
    if maximum is not None and number > maximum:
        _fail(
            f"{field} must be <= {maximum}",
            details={"field": field, "value": number, "maximum": maximum},
        )
    return _tidy(number)


def _tidy(value: float) -> float:
    rounded = round(float(value), MAX_VALUE_DECIMALS)
    return 0.0 if rounded == 0 else rounded


def _aware(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{field} must be an RFC 3339 string", details={"field": field})
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        _fail(f"{field} is not a valid datetime", details={"field": field, "value": value[:64]})
    if parsed.tzinfo is None:
        _fail(f"{field} must include a timezone", details={"field": field})
    return parsed


def _optional_int(value: Any, field: str, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{field} must be an integer", details={"field": field})
    if value < minimum or value > maximum:
        _fail(
            f"{field} must be between {minimum} and {maximum}",
            details={"field": field, "value": value},
        )
    return value


def _canonical_unit(kind: str, unit: Any) -> str:
    raw = _text(unit, "unit", max_length=32) or ""
    key = raw.strip().lower().replace(" ", "")
    canonical = UNIT_ALIASES.get(key)
    if canonical is None:
        _fail(
            "unit is not recognised",
            code="invalid_unit",
            details={"kind": kind, "unit": raw},
        )
    assert canonical is not None
    return canonical


def _convert_value(kind: str, value: float, unit: str) -> tuple[float, str]:
    """把少数常见单位换算到规范单位；其余只校验不换算。"""
    if kind == "body-mass" and unit == "lb":
        return _tidy(value * 0.45359237), "kg"
    if kind == "blood-pressure" and unit == "kPa":
        return _tidy(value * 7.50062), "mm[Hg]"
    if kind == "body-temperature" and unit == "°F":
        return _tidy((value - 32.0) * 5.0 / 9.0), "Cel"
    if kind == "ecg" and unit == "uV":
        return _tidy(value * 0.001), "mV"
    if kind == "ecg" and unit == "V":
        return _tidy(value * 1000.0), "mV"
    return _tidy(value), unit


def _require_unit(spec: KindSpec, unit: str) -> str:
    if unit not in spec.units:
        _fail(
            f"unit {unit} is not allowed for {spec.kind}",
            code="invalid_unit",
            details={"kind": spec.kind, "unit": unit, "allowed": list(spec.units)},
        )
    return unit


def _safe_relative(value: Any, field: str) -> str:
    raw = _text(value, field, max_length=256) or ""
    if "\\" in raw or "\x00" in raw:
        _fail(f"{field} must use forward slashes", details={"field": field})
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        _fail(f"{field} is not a safe relative path", details={"field": field, "path": raw})
    if ":" in raw:
        _fail(f"{field} must not contain a drive or scheme", details={"field": field})
    return candidate.as_posix()


# --------------------------------------------------------------------------- #
# value 校验
# --------------------------------------------------------------------------- #


def _normalize_value(
    kind: str, raw: Any, unit: str
) -> tuple[Any, str, dict[str, Any]]:
    """返回 ``(value, unit, extra)``；``extra`` 放 metric 等附加字段。"""
    extra: dict[str, Any] = {}
    if kind == "steps":
        return _number(raw, "value", minimum=0, maximum=200_000), _require_unit(
            KIND_SPECS[kind], unit
        ), extra
    if kind in {"heart-rate", "resting-heart-rate"}:
        maximum = 300.0 if kind == "heart-rate" else 200.0
        return _number(raw, "value", minimum=20, maximum=maximum), _require_unit(
            KIND_SPECS[kind], unit
        ), extra
    if kind == "sleep":
        stage = _text(raw, "value", max_length=32) or ""
        if stage not in SLEEP_STAGES:
            _fail(
                "sleep stage is not recognised",
                code="invalid_value",
                details={"kind": kind, "value": stage, "allowed": sorted(SLEEP_STAGES)},
            )
        return stage, _require_unit(KIND_SPECS[kind], unit), extra
    if kind == "body-mass":
        number, canonical = _convert_value(kind, _number(raw, "value", minimum=0.01, maximum=5000), unit)
        if number < 1 or number > 500:
            _fail("body mass is out of range (1–500 kg)", details={"value": number})
        return number, _require_unit(KIND_SPECS[kind], canonical), extra
    if kind == "blood-pressure":
        if not isinstance(raw, dict):
            _fail("blood-pressure value must be an object", details={"kind": kind})
        unknown = set(raw) - {"systolic", "diastolic"}
        if unknown:
            _fail("blood-pressure has unexpected fields", details={"fields": sorted(unknown)})
        systolic_raw, canonical = _convert_value(
            kind, _number(raw.get("systolic"), "value.systolic", minimum=0, maximum=10000), unit
        )
        diastolic_raw, _ = _convert_value(
            kind, _number(raw.get("diastolic"), "value.diastolic", minimum=0, maximum=10000), unit
        )
        systolic, diastolic = _tidy(systolic_raw), _tidy(diastolic_raw)
        if not 40 <= systolic <= 300:
            _fail("systolic is out of range (40–300)", code="invalid_value", details={"value": systolic})
        if not 20 <= diastolic <= 200:
            _fail(
                "diastolic is out of range (20–200)", code="invalid_value", details={"value": diastolic}
            )
        if systolic <= diastolic:
            _fail(
                "systolic must be greater than diastolic",
                code="invalid_value",
                details={"systolic": systolic, "diastolic": diastolic},
            )
        return {"systolic": systolic, "diastolic": diastolic}, _require_unit(
            KIND_SPECS[kind], canonical
        ), extra
    if kind == "spo2":
        return _number(raw, "value", minimum=0, maximum=100), _require_unit(
            KIND_SPECS[kind], unit
        ), extra
    if kind == "stress":
        return _number(raw, "value", minimum=0, maximum=100), _require_unit(
            KIND_SPECS[kind], unit
        ), extra
    if kind == "workout":
        if not isinstance(raw, dict):
            _fail("workout value must be an object", details={"kind": kind})
        allowed = {"activity", "durationSec", "distanceM", "energyKcal", "avgHeartRate"}
        unknown = set(raw) - allowed
        if unknown:
            _fail("workout has unexpected fields", details={"fields": sorted(unknown)})
        activity = _text(raw.get("activity"), "value.activity", max_length=64) or ""
        duration = _number(raw.get("durationSec"), "value.durationSec", minimum=0, maximum=604800)
        normalized: dict[str, Any] = {"activity": activity, "durationSec": duration}
        if raw.get("distanceM") is not None:
            normalized["distanceM"] = _number(
                raw.get("distanceM"), "value.distanceM", minimum=0, maximum=1_000_000
            )
        if raw.get("energyKcal") is not None:
            normalized["energyKcal"] = _number(
                raw.get("energyKcal"), "value.energyKcal", minimum=0, maximum=100_000
            )
        if raw.get("avgHeartRate") is not None:
            normalized["avgHeartRate"] = _number(
                raw.get("avgHeartRate"), "value.avgHeartRate", minimum=20, maximum=300
            )
        return normalized, _require_unit(KIND_SPECS[kind], unit), extra
    if kind == "respiratory-rate":
        return _number(raw, "value", minimum=2, maximum=80), _require_unit(
            KIND_SPECS[kind], unit
        ), extra
    if kind == "body-temperature":
        number, canonical = _convert_value(
            kind, _number(raw, "value", minimum=-100, maximum=300), unit
        )
        if not 25 <= number <= 45:
            _fail(
                "body temperature is out of range (25–45 Cel)",
                code="invalid_value",
                details={"value": number},
            )
        return number, _require_unit(KIND_SPECS[kind], canonical), extra
    if kind == "blood-glucose":
        canonical = _require_unit(KIND_SPECS[kind], unit)
        if canonical == "mg/dL":
            return _number(raw, "value", minimum=10, maximum=1000), canonical, extra
        return _number(raw, "value", minimum=0.5, maximum=60), canonical, extra
    if kind == "hrv":
        if not isinstance(raw, dict):
            _fail("hrv value must be an object", details={"kind": kind})
        unknown = set(raw) - {"metric", "value"}
        if unknown:
            _fail("hrv has unexpected fields", details={"fields": sorted(unknown)})
        metric = (_text(raw.get("metric"), "value.metric", max_length=32) or "").lower()
        number = _number(raw.get("value"), "value.value", minimum=0, maximum=5000)
        canonical = _require_unit(KIND_SPECS[kind], unit)
        expected = HRV_UNIT_BY_METRIC.get(metric)
        if expected is not None and canonical != expected:
            _fail(
                f"hrv metric {metric} must use unit {expected}",
                code="invalid_unit",
                details={"metric": metric, "unit": canonical, "allowed": [expected]},
            )
        extra["metric"] = metric
        return {"metric": metric, "value": number}, canonical, extra
    if kind == "ecg":
        if not isinstance(raw, dict):
            _fail("ecg value must be an object", details={"kind": kind})
        unknown = set(raw) - {"samplingRate", "lead", "sampleCount"}
        if unknown:
            _fail("ecg has unexpected fields", details={"fields": sorted(unknown)})
        normalized: dict[str, Any] = {}
        if raw.get("samplingRate") is not None:
            normalized["samplingRate"] = _number(
                raw.get("samplingRate"), "value.samplingRate", minimum=1, maximum=100_000
            )
        if raw.get("lead") is not None:
            normalized["lead"] = _lead_name(raw.get("lead"))
        if raw.get("sampleCount") is not None:
            normalized["sampleCount"] = _number(
                raw.get("sampleCount"), "value.sampleCount", minimum=1, maximum=5_000_000
            )
        return normalized, _canonical_unit(kind, unit), extra
    if kind == "body":
        if not isinstance(raw, dict):
            _fail("body value must be an object", details={"kind": kind})
        unknown = set(raw) - set(BODY_METRIC_RANGES)
        if unknown:
            _fail("body has unexpected fields", details={"fields": sorted(unknown)})
        if not raw:
            _fail("body requires at least one composition metric", details={"kind": kind})
        normalized = {}
        for key, (minimum, maximum) in BODY_METRIC_RANGES.items():
            if raw.get(key) is None:
                continue
            normalized[key] = _number(raw.get(key), f"value.{key}", minimum=minimum, maximum=maximum)
        return normalized, _require_unit(KIND_SPECS[kind], unit), extra

    _fail("unsupported kind", code="invalid_kind", details={"kind": kind})
    raise AssertionError("unreachable")  # pragma: no cover


def _lead_name(value: Any) -> str:
    lead = _text(value, "lead", max_length=16) or ""
    if not lead or not lead[0].isalpha():
        _fail("lead must start with a letter", code="invalid_value", details={"lead": lead})
    if any(not (ch.isalnum() or ch in "+-") for ch in lead):
        _fail("lead contains unsupported characters", code="invalid_value", details={"lead": lead})
    return lead


# --------------------------------------------------------------------------- #
# 结构化字段
# --------------------------------------------------------------------------- #


def _normalize_source(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail("source must be an object", details={"field": "source"})
    unknown = set(raw) - {"kind", "app", "device", "manufacturer"}
    if unknown:
        _fail("source has unexpected fields", details={"fields": sorted(unknown)})
    kind = _text(raw.get("kind"), "source.kind", max_length=16) or "unknown"
    if kind not in SOURCE_KINDS:
        _fail(
            "source.kind is not recognised",
            code="invalid_value",
            details={"sourceKind": kind, "allowed": sorted(SOURCE_KINDS)},
        )
    source: dict[str, Any] = {"kind": kind}
    for key in ("app", "device", "manufacturer"):
        value = raw.get(key)
        if value is None:
            continue
        source[key] = _text(value, f"source.{key}", max_length=64)
    return source


def _normalize_evidence(raw: Any, files: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail("evidence must be an object", details={"field": "evidence"})
    unknown = set(raw) - {"file", "locator", "snippet", "page", "line"}
    if unknown:
        _fail("evidence has unexpected fields", details={"fields": sorted(unknown)})
    file_name = _text(raw.get("file"), "evidence.file", max_length=512) or ""
    normalized_file = file_name.replace("\\", "/")
    top = normalized_file.split("/", 1)[0]
    if top not in files:
        _fail(
            "evidence.file is not one of this session's uploaded files",
            code="evidence_file_unknown",
            details={"file": normalized_file, "files": sorted(files)[:20]},
        )
    evidence: dict[str, Any] = {"file": normalized_file}
    locator = _text(raw.get("locator"), "evidence.locator", max_length=200, required=False)
    snippet = _text(raw.get("snippet"), "evidence.snippet", max_length=500, required=False)
    page = _optional_int(raw.get("page"), "evidence.page", minimum=1, maximum=100_000)
    line = _optional_int(raw.get("line"), "evidence.line", minimum=1, maximum=10_000_000)
    if locator is None and snippet is None and page is None and line is None:
        _fail(
            "evidence requires locator, snippet, page or line",
            code="evidence_incomplete",
            details={"file": normalized_file},
        )
    if locator is not None:
        evidence["locator"] = locator
    if snippet is not None:
        evidence["snippet"] = snippet
    if page is not None:
        evidence["page"] = page
    if line is not None:
        evidence["line"] = line
    return evidence


def _normalize_waveform(raw: Any, unit: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail(
            "kind=ecg requires a waveform object from the output/ directory",
            code="ecg_waveform_required",
            details={"field": "waveform"},
        )
    allowed = {"file", "format", "column", "timeColumn", "unit", "lead", "samplingRate"}
    unknown = set(raw) - allowed
    if unknown:
        _fail("waveform has unexpected fields", details={"fields": sorted(unknown)})
    file_name = _safe_relative(raw.get("file"), "waveform.file")
    # Agent 常写 "output/ecg.csv"；waveform.file 是相对 output/ 的路径，接受两种写法。
    if file_name.lower().startswith("output/"):
        file_name = file_name[len("output/") :]
    fmt = (_text(raw.get("format"), "waveform.format", max_length=16, required=False) or "csv").lower()
    if fmt in {"float32", "bin", "f32"}:
        fmt = "f32"
    if fmt not in {"csv", "f32"}:
        _fail(
            "waveform.format must be csv or f32",
            code="invalid_value",
            details={"format": fmt},
        )
    waveform: dict[str, Any] = {"file": file_name, "format": fmt}
    column = raw.get("column")
    if column is not None:
        if isinstance(column, bool):
            _fail("waveform.column must be an integer or a column name")
        if isinstance(column, int):
            if column < 0 or column > 1000:
                _fail("waveform.column is out of range", details={"column": column})
            waveform["column"] = column
        elif isinstance(column, str):
            waveform["column"] = _text(column, "waveform.column", max_length=64)
        else:
            _fail("waveform.column must be an integer or a column name")
    time_column = raw.get("timeColumn")
    if time_column is not None:
        if isinstance(time_column, bool) or not isinstance(time_column, (int, str)):
            _fail("waveform.timeColumn must be an integer or a column name")
        if isinstance(time_column, int) and (time_column < 0 or time_column > 1000):
            _fail("waveform.timeColumn is out of range", details={"timeColumn": time_column})
        waveform["timeColumn"] = time_column
    if raw.get("samplingRate") is not None:
        waveform["samplingRate"] = _number(
            raw.get("samplingRate"), "waveform.samplingRate", minimum=1, maximum=100_000
        )
    if raw.get("lead") is not None:
        waveform["lead"] = _lead_name(raw.get("lead"))
    if raw.get("unit") is not None:
        waveform["unit"] = _canonical_unit("ecg", raw.get("unit"))
    else:
        waveform["unit"] = unit
    return waveform


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _fail("tags must be an array", details={"field": "tags"})
    if len(raw) > 8:
        _fail("tags supports at most 8 items", details={"count": len(raw)})
    tags: list[str] = []
    for item in raw:
        tag = _text(item, "tags[]", max_length=32) or ""
        if tag not in tags:
            tags.append(tag)
    return tags


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


def new_proposal_id() -> str:
    return f"prp_{uuid7().hex}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def proposal_fingerprint(normalized: dict[str, Any]) -> str:
    basis = {
        key: normalized.get(key)
        for key in (
            "kind",
            "value",
            "unit",
            "startAt",
            "endAt",
            "source",
            "evidence",
            "confidence",
            "metric",
            "waveform",
        )
    }
    return hashlib.sha256(canonical_json(basis).encode("utf-8")).hexdigest()


def normalize_record(raw: Any, *, files: set[str]) -> dict[str, Any]:
    """校验并规范化一条候选；非法时抛 ``RecordValidationError``。"""
    if not isinstance(raw, dict):
        _fail("record must be an object", details={"type": type(raw).__name__})
    unknown = set(raw) - ALLOWED_KEYS
    if unknown:
        _fail(
            "record has unexpected fields",
            code="unexpected_field",
            details={"fields": sorted(unknown)},
        )

    kind = _text(raw.get("kind"), "kind", max_length=64) or ""
    spec = KIND_SPECS.get(kind)
    if spec is None:
        _fail(
            "kind is not supported",
            code="invalid_kind",
            details={"kind": kind, "allowed": list(KIND_NAMES)},
        )
    assert spec is not None

    start = _aware(raw.get("startAt"), "startAt")
    end = _aware(raw.get("endAt"), "endAt") if raw.get("endAt") is not None else None
    if end is not None and end < start:
        _fail("endAt must not be before startAt", details={"startAt": start.isoformat(), "endAt": end.isoformat()})
    if spec.end_required and end is None:
        _fail(f"kind {kind} requires endAt", details={"kind": kind})
    duration = _tidy((end - start).total_seconds()) if end is not None else None
    if duration is not None and duration < 0:  # 防御：上面已检查
        _fail("duration must not be negative", details={"durationSec": duration})

    unit = _canonical_unit(kind, raw.get("unit"))
    value, unit, extra = _normalize_value(kind, raw.get("value"), unit)

    source = _normalize_source(raw.get("source"))
    evidence = _normalize_evidence(raw.get("evidence"), files)
    confidence = _number(raw.get("confidence"), "confidence", minimum=0, maximum=1)
    tags = _normalize_tags(raw.get("tags"))
    notes = _text(raw.get("notes"), "notes", max_length=MAX_TEXT, required=False) or ""

    waveform = None
    if kind == "ecg":
        if raw.get("waveform") is None:
            _fail(
                "kind=ecg requires waveform (PDF reports must only produce numeric records)",
                code="ecg_waveform_required",
                details={"kind": kind},
            )
        waveform = _normalize_waveform(raw.get("waveform"), unit)
        unit = "mV"

    start_iso = start.isoformat()
    end_iso = end.isoformat() if end is not None else None
    payload: dict[str, Any] = {
        "kind": kind,
        "value": value,
        "unit": unit,
        "startAt": start_iso,
        "endAt": end_iso,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
    }
    if extra.get("metric"):
        payload["metric"] = extra["metric"]
    if waveform is not None:
        payload["waveform"] = waveform

    record: dict[str, Any] = {
        "id": new_proposal_id(),
        "kind": kind,
        "recordType": spec.record_type,
        "value": value,
        "unit": unit,
        "startAt": start_iso,
        "endAt": end_iso,
        "durationSec": duration,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
        "tags": tags,
        "notes": notes,
        "payload": payload,
        "createdAt": datetime.now(UTC).isoformat(),
    }
    if extra.get("metric"):
        record["metric"] = extra["metric"]
    if waveform is not None:
        record["waveform"] = waveform
    record["fingerprint"] = proposal_fingerprint(record)
    return record


def record_type_for(kind: str) -> str:
    spec = KIND_SPECS.get(kind)
    if spec is None:
        raise KeyError(kind)
    return spec.record_type


def external_id(
    *,
    file_hash: str,
    source: dict[str, Any],
    kind: str,
    start_at: str,
    end_at: str | None,
    value: Any,
) -> str:
    """幂等键：同文件 + 同来源 + 同 kind + 同时间 + 同值只写一次。"""
    source_label = "|".join(
        str(source.get(key) or "") for key in ("kind", "app", "device", "manufacturer")
    )
    start = datetime.fromisoformat(start_at).astimezone(UTC).isoformat()
    end = datetime.fromisoformat(end_at).astimezone(UTC).isoformat() if end_at else ""
    basis = "|".join(
        [
            file_hash,
            source_label,
            kind,
            start,
            end,
            canonical_json(value),
        ]
    )
    return f"sha256:{hashlib.sha256(basis.encode('utf-8')).hexdigest()}"


__all__ = [
    "ADAPTER_VERSION",
    "ECG_RECORD_TYPE",
    "HEALTH_PREFIX",
    "KIND_NAMES",
    "KIND_SPECS",
    "KindSpec",
    "canonical_json",
    "external_id",
    "new_proposal_id",
    "normalize_record",
    "proposal_fingerprint",
    "record_type_for",
]

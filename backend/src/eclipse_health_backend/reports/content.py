"""报告内容：把记录、信号、分析结果组装成与格式无关的数据模型。

渲染层（PDF / PNG）只消费 ``ReportContent``；脱敏也在这一层完成，
保证「内容模型里不含姓名/备注」这一约束可以被单元测试直接验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from sqlmodel import Session

from .. import __version__
from ..analysis.ids import rfc3339
from ..db import analysis_repo
from ..db.models import AnalysisTable, RecordTable
from ..db.repositories import get_member_row, list_signal_rows, record_from_row
from ..domain.common import utc_now
from ..domain.errors import ApiError
from ..storage.files import decode_float32, read_signal

SCHEMA_REPORT = "org.eclipsehealth.report/1"

DISCLAIMER = (
    "本报告由 eclipse health 在本地生成，仅供研究与健康教育参考，"
    "不构成医疗诊断、治疗建议或用药依据。如有不适或异常，请及时就医。"
)
WATERMARK = "非诊断 · 仅供健康参考"

TEMPLATE_LABELS = {
    "simple": "简洁版",
    "detailed": "详细版",
    "doctor": "医生版",
}

CLASS_LABELS = {
    "N": "正常心搏",
    "SVEB": "室上性异位",
    "VEB": "室性异位",
    "F": "融合搏动",
}
CLASS_ORDER = ("N", "SVEB", "VEB", "F")

KEY_METRIC_CODES = (
    "heart_rate_mean",
    "heart_rate_min",
    "heart_rate_max",
    "rr_mean",
    "sdnn",
    "rmssd",
    "pnn50",
    "n_ratio",
    "svb_ratio",
    "veb_ratio",
    "f_ratio",
)

MODEL_CARD: dict[str, Any] = {
    "modelId": "cardia-2.0",
    "name": "Cardia 2.0",
    "task": "beat-classification",
    "trainingData": "MIT-BIH Arrhythmia Database (MLII)",
    "input": {
        "leads": ["MLII"],
        "fs": 360,
        "windowSamples": 180,
        "beatsPerWindow": 64,
        "features": "cardia-104d",
    },
    "output": {"classes": ["N", "SVEB", "VEB", "F"]},
    "parameters": 722327,
    "nonDiagnostic": True,
    "limitations": [
        "仅支持单导联（MLII）",
        "训练与评估基于 360 Hz",
        "未实现波形 delineation（QRS/PR/QT 不可用）",
        "研究/教育用途，非医疗器械",
    ],
}

DEFAULT_WINDOW_SECONDS = 12.0


@dataclass
class Waveform:
    """报告里展示的波形切片（默认前 12 秒）。"""

    samples: np.ndarray
    fs: float
    lead: str
    start_sec: float
    duration_sec: float
    rpeaks: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class ReportContent:
    report_id: str
    record_id: str
    analysis_id: str
    template: str
    redacted: bool
    generated_at: datetime
    captured_at: datetime
    timezone: str
    device: str
    source_kind: str
    member_name: str
    notes: str | None
    leads: list[str]
    fs: float
    duration_sec: float
    window_seconds: float
    waveform: Waveform | None
    metrics: dict[str, float | None]
    class_counts: dict[str, int]
    class_ratios: dict[str, float | None]
    measurements: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    quality_score: float | None
    quality_level: str | None
    beats_total: int
    model_version: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=lambda: dict(MODEL_CARD))
    app_name: str = "eclipse health"
    app_version: str = __version__

    @property
    def template_label(self) -> str:
        return TEMPLATE_LABELS.get(self.template, self.template)

    @property
    def watermark(self) -> str | None:
        """脱敏报告带水印；未脱敏报告只保留页脚免责声明。"""
        return WATERMARK if self.redacted else None

    def local_captured_at(self) -> datetime:
        return _to_zone(self.captured_at, self.timezone)

    def local_generated_at(self) -> datetime:
        return _to_zone(self.generated_at, self.timezone)

    def as_dict(self) -> dict[str, Any]:
        """可序列化的内容快照（测试脱敏用，不含任何原始文件名）。"""
        return {
            "reportId": self.report_id,
            "recordId": self.record_id,
            "analysisId": self.analysis_id,
            "template": self.template,
            "redacted": self.redacted,
            "generatedAt": rfc3339(self.generated_at),
            "capturedAt": rfc3339(self.captured_at),
            "timezone": self.timezone,
            "device": self.device,
            "sourceKind": self.source_kind,
            "memberName": self.member_name,
            "notes": self.notes,
            "leads": list(self.leads),
            "fs": self.fs,
            "durationSec": self.duration_sec,
            "metrics": dict(self.metrics),
            "classCounts": dict(self.class_counts),
            "classRatios": dict(self.class_ratios),
            "measurements": [dict(item) for item in self.measurements],
            "warnings": [dict(item) for item in self.warnings],
            "qualityScore": self.quality_score,
            "qualityLevel": self.quality_level,
            "beatsTotal": self.beats_total,
            "modelVersion": self.model_version,
            "parameters": dict(self.parameters),
            "provenance": dict(self.provenance),
            "model": dict(self.model),
        }


def build_report_content(
    session: Session,
    record_row: RecordTable,
    analysis_row: AnalysisTable,
    *,
    template: str,
    redact: bool,
    report_id: str,
    generated_at: datetime | None = None,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> ReportContent:
    record = record_from_row(record_row)
    data = dict(analysis_row.data or {})
    beats = [beat for beat in (data.get("beats") or []) if isinstance(beat, dict)]
    measurements = data.get("measurements") or analysis_repo.measurements_for(
        session, analysis_row.id
    )
    measurements = [dict(item) for item in measurements if isinstance(item, dict)]
    by_code = {str(item.get("code")): item for item in measurements}

    warnings = _collect_warnings(data, measurements)
    warning_extra: list[dict[str, Any]] = []

    member = get_member_row(session, record.memberId)
    member_name = "匿名"
    notes: str | None = None
    if not redact:
        member_name = member.display_name if member is not None else "本人"
        notes = record.notes or None

    waveform = _build_waveform(session, record_row, record, beats, window_seconds, warning_extra)
    warnings.extend(warning_extra)

    quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}
    quality_score = _as_float(quality.get("score"))
    quality_level = quality.get("level") if isinstance(quality.get("level"), str) else None

    class_counts = _class_counts(beats)
    class_ratios = {
        label: _ratio_for(by_code, label, class_counts, len(beats))
        for label in CLASS_ORDER
    }
    metrics = {code: _measurement_value(by_code, code) for code in KEY_METRIC_CODES}
    # 比例以逐搏计数为准，测量值缺失时也能显示。
    ratio_codes = {"N": "n_ratio", "SVEB": "svb_ratio", "VEB": "veb_ratio", "F": "f_ratio"}
    for label, code in ratio_codes.items():
        if metrics.get(code) is None:
            metrics[code] = class_ratios.get(label)

    source = record.source
    device_parts = [part for part in (source.manufacturer, source.device) if part]
    device = " ".join(device_parts) if device_parts else "未标注"

    return ReportContent(
        report_id=report_id,
        record_id=record.id,
        analysis_id=analysis_row.id,
        template=template,
        redacted=redact,
        generated_at=generated_at or utc_now(),
        captured_at=record.capturedAt,
        timezone=record.timezone,
        device=device,
        source_kind=source.kind,
        member_name=member_name,
        notes=notes,
        leads=list(record.leads),
        fs=float(record.samplingRate or (waveform.fs if waveform else 0.0)),
        duration_sec=float(record.durationSec or 0.0),
        window_seconds=window_seconds,
        waveform=waveform,
        metrics=metrics,
        class_counts=class_counts,
        class_ratios=class_ratios,
        measurements=measurements,
        warnings=warnings,
        quality_score=quality_score,
        quality_level=quality_level,
        beats_total=len(beats),
        model_version=str(data.get("modelVersion") or ""),
        parameters=dict(data.get("parameters") or {}),
        provenance=dict(data.get("provenance") or {}),
    )


def _measurement_value(by_code: dict[str, dict[str, Any]], code: str) -> float | None:
    item = by_code.get(code)
    if not item:
        return None
    return _as_float(item.get("value"))


def _ratio_for(
    by_code: dict[str, dict[str, Any]],
    label: str,
    class_counts: dict[str, int],
    total: int,
) -> float | None:
    code = {"N": "n_ratio", "SVEB": "svb_ratio", "VEB": "veb_ratio", "F": "f_ratio"}[label]
    value = _measurement_value(by_code, code)
    if value is not None:
        return value
    if total <= 0:
        return None
    return round(class_counts.get(label, 0) / total * 100.0, 2)


def _class_counts(beats: list[dict[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in CLASS_ORDER}
    for beat in beats:
        label = str(beat.get("label") or "")
        if label in counts:
            counts[label] += 1
    return counts


def _collect_warnings(
    data: dict[str, Any], measurements: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in (
        data.get("warnings") or [],
        (data.get("quality") or {}).get("warnings") if isinstance(data.get("quality"), dict) else [],
    ):
        for warning in source or []:
            if not isinstance(warning, dict):
                continue
            code = str(warning.get("code") or "warning")
            message = str(warning.get("message") or code)
            severity = str(warning.get("severity") or "warning")
            items.append(
                {
                    "code": code,
                    "message": message,
                    "severity": severity,
                    "startSec": warning.get("startSec"),
                    "endSec": warning.get("endSec"),
                }
            )
    for measurement in measurements:
        for warning in measurement.get("warnings") or []:
            if not isinstance(warning, dict):
                continue
            code = str(warning.get("code") or "warning")
            items.append(
                {
                    "code": code,
                    "message": str(warning.get("message") or code),
                    "severity": str(warning.get("severity") or "warning"),
                    "startSec": None,
                    "endSec": None,
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["code"], item["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_waveform(
    session: Session,
    record_row: RecordTable,
    record: Any,
    beats: list[dict[str, Any]],
    window_seconds: float,
    warning_sink: list[dict[str, Any]],
) -> Waveform | None:
    rows = list_signal_rows(session, record_row.id)
    if not rows:
        return None
    preferred = next((row for row in rows if row.lead in record.leads), rows[0])
    try:
        raw = read_signal(preferred.relative_path, preferred.sha256)
    except ApiError:
        warning_sink.append(
            {
                "code": "waveform_unavailable",
                "message": "波形文件缺失或校验失败，报告未包含波形",
                "severity": "warning",
                "startSec": None,
                "endSec": None,
            }
        )
        return None
    samples = decode_float32(raw)
    fs = float(preferred.fs or record.samplingRate or 0.0)
    if fs <= 0 or samples.size == 0:
        return None
    limit = max(1, min(samples.size, round(fs * window_seconds)))
    window = np.asarray(samples[:limit], dtype=np.float64)
    marks: list[tuple[int, str]] = []
    for beat in beats:
        position = beat.get("rPeakSample")
        if not isinstance(position, (int, float)):
            continue
        index = int(position)
        if 0 <= index < window.size:
            marks.append((index, str(beat.get("label") or "N")))
    return Waveform(
        samples=window,
        fs=fs,
        lead=preferred.lead,
        start_sec=0.0,
        duration_sec=window.size / fs,
        rpeaks=marks,
    )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _to_zone(value: datetime, tz_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = UTC
    return value.astimezone(zone)


def format_datetime(value: datetime, tz_name: str) -> str:
    return _to_zone(value, tz_name).strftime("%Y-%m-%d %H:%M")


def format_duration(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "—"
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_metric(value: float | None, unit: str = "") -> str:
    if value is None:
        return "—"
    if unit == "%":
        text = f"{value:.1f}"
    elif abs(value) >= 100:
        text = f"{value:.0f}"
    else:
        text = f"{value:.1f}"
    return f"{text}{unit}"


__all__ = [
    "CLASS_LABELS",
    "CLASS_ORDER",
    "DEFAULT_WINDOW_SECONDS",
    "DISCLAIMER",
    "KEY_METRIC_CODES",
    "MODEL_CARD",
    "SCHEMA_REPORT",
    "TEMPLATE_LABELS",
    "WATERMARK",
    "ReportContent",
    "Waveform",
    "build_report_content",
    "format_datetime",
    "format_duration",
    "format_metric",
]

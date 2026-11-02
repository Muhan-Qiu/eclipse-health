"""Samsung Health 数据导出（``samsunghealth_*`` 目录 / ZIP）。

真实导出是一组 CSV：第一行是 ``com.samsung.xxx,<device>,<version>`` 元数据，
第二行才是列名。常见文件包括步数、心率、压力、睡眠、运动、体重、呼吸率。

这里直接把这些 CSV 转成 eclipse health 的健康记录：
- 步数按「本地日」汇总；
- 心率按小时记录（min/max 写入 payload）；
- 压力、睡眠、运动、体重、呼吸率逐条映射；
- 未映射的文件只给出警告，不猜测。
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import limits
from .base import (
    Detection,
    HealthRecordDraft,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParseParameters,
    PreviewData,
    warning,
)
from .errors import invalid_file

PREFIXES = ("com.samsung.shealth.", "com.samsung.health.")
KIND_RECORD_TYPES = {
    "steps": "org.eclipsehealth.health.steps",
    "heart-rate": "org.eclipsehealth.health.heart-rate",
    "sleep": "org.eclipsehealth.health.sleep",
    "body-mass": "org.eclipsehealth.health.body-mass",
    "stress": "org.eclipsehealth.health.stress",
    "workout": "org.eclipsehealth.health.workout",
    "respiratory-rate": "org.eclipsehealth.health.respiratory-rate",
}
COUNT_KEYS = {
    "steps": "steps",
    "heart-rate": "heartRate",
    "sleep": "sleep",
    "body-mass": "bodyMass",
    "stress": "stress",
    "workout": "workout",
    "respiratory-rate": "respiratoryRate",
}

# Samsung activity_type 的常用值（未列出的保留原始编号）。
ACTIVITY_TYPES = {
    "1001": "walking",
    "1002": "running",
    "1003": "cycling",
    "1101": "hiking",
    "1301": "swimming",
    "1401": "exercise",
    "1501": "strength-training",
    "1601": "yoga",
}


@dataclass(slots=True)
class _Scan:
    drafts: list[HealthRecordDraft] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)

    def add(self, draft: HealthRecordDraft) -> None:
        self.drafts.append(draft)
        key = COUNT_KEYS.get(draft.kind, draft.kind)
        self.counts[key] = self.counts.get(key, 0) + 1


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _tidy(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(value, 6)


def _parse_offset(value: str | None) -> timezone:
    text = str(value or "").strip().upper().replace(":", "")
    if text.startswith("UTC") and len(text) >= 8:
        sign = -1 if text[3] == "-" else 1
        try:
            hours = int(text[4:6])
            minutes = int(text[7:9]) if len(text) >= 9 else 0
        except ValueError:
            return UTC
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    return UTC


def _parse_time(value: str | None, offset: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return moment.replace(tzinfo=_parse_offset(offset))
    return None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _external(stem: str, *parts: Any) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]
    return f"samsung:{stem}:{digest}"


def _source_app() -> str:
    return "Samsung Health"


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]] | None:
    """Samsung CSV：第 1 行元数据，第 2 行表头，之后是数据。"""
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    reader = csv.reader(io.StringIO(text))
    try:
        first = next(reader)
    except StopIteration:
        return None
    if not first or not first[0].startswith(PREFIXES):
        return None
    try:
        header = next(reader)
    except StopIteration:
        return None
    header = [cell.strip() for cell in header]
    rows: list[dict[str, str]] = []
    for cells in reader:
        if not cells or not any(cell.strip() for cell in cells):
            continue
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells, strict=False)))
    return header, rows


def _stem(name: str) -> str:
    """去掉扩展名与导出时的 14 位时间戳。"""
    return re.sub(r"\.\d{14}$", "", Path(name).stem)


def _find_samsung_files(root: Path) -> dict[str, Path]:
    """按文件名主干归类；同一种类型只取第一个文件。"""
    found: dict[str, Path] = {}
    for path in root.rglob("*.csv"):
        name = path.name
        if not name.startswith(PREFIXES):
            continue
        found.setdefault(_stem(name), path)
    return found


class SamsungHealthAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.samsung-health"
    adapter_version = "1.0.0"
    format = "samsung-health"

    # ---------------------------------------------------------------- detect
    def detect(self, source: ImportSource) -> Detection | None:
        if source.path.is_file() and source.path.suffix.lower() == ".csv":
            if not source.path.name.startswith(PREFIXES):
                return None
            return Detection(self.format, 0.92, "Samsung Health CSV")
        root = source.extracted_dir or (source.path if source.path.is_dir() else None)
        if root is None:
            return None
        files = _find_samsung_files(root)
        if not files:
            return None
        if len(files) >= 2:
            return Detection(self.format, 0.98, "Samsung Health 导出目录")
        return Detection(self.format, 0.9, "Samsung Health CSV")

    # ---------------------------------------------------------------- build
    def _build(self, source: ImportSource) -> ParsedImport:
        if source.path.is_file() and source.path.suffix.lower() == ".csv":
            paths = {_stem(source.path.name): source.path}
        else:
            root = source.extracted_dir or source.path
            paths = _find_samsung_files(root)
        if not paths:
            raise invalid_file(
                "没有找到 Samsung Health 导出 CSV",
                code="samsung_export_missing",
            )
        scan = _Scan()
        for stem, path in sorted(paths.items()):
            self._scan_file(stem, path, scan)

        if not scan.drafts:
            raise invalid_file(
                "Samsung 导出里没有可导入的步数/心率/睡眠/压力/运动/体重/呼吸率记录",
                code="samsung_export_empty",
                details={"files": len(paths)},
            )
        total = len(scan.drafts)
        if total > limits.HEALTH_MAX_RECORDS:
            raise invalid_file(
                f"记录数超过 {limits.HEALTH_MAX_RECORDS} 条上限",
                code="import_too_many_records",
                details={"records": total, "limit": limits.HEALTH_MAX_RECORDS},
            )
        warnings = list(scan.warnings)
        if scan.ignored:
            warnings.append(
                warning(
                    "samsung_unmapped_files",
                    "已跳过未映射的 Samsung 文件：" + ", ".join(scan.ignored[:10]),
                    severity="info",
                )
            )
        warnings.append(
            warning(
                "samsung_health_imported",
                f"Samsung Health 导出：{total} 条健康记录",
                severity="info",
            )
        )
        return ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=0.0,
            duration_sec=0.0,
            leads=[],
            primary_lead="",
            metadata={"importSource": "samsung-health", "format": self.format},
            warnings=warnings,
            health_records=scan.drafts,
            record_counts=dict(scan.counts),
            total_records=total,
            import_source="samsung-health",
        )

    def preview(self, source: ImportSource) -> PreviewData:
        parsed = self._build(source)
        return PreviewData(
            sampling_rate=None,
            leads=[],
            duration_sec=None,
            unit="1",
            requires_sampling_rate=False,
            requires_lead=False,
            requires_unit=False,
            warnings=list(parsed.warnings),
            n_samples=0,
            samples=[],
            record_counts=dict(parsed.record_counts),
            total_records=parsed.total_records,
        )

    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        return self._build(source)

    # ---------------------------------------------------------------- files
    def _scan_file(self, stem: str, path: Path, scan: _Scan) -> None:
        table = _read_csv(path)
        if table is None:
            scan.ignored.append(path.name)
            return
        _header, rows = table
        if not rows:
            return
        if stem == "com.samsung.shealth.tracker.pedometer_step_count":
            self._steps(rows, scan)
        elif stem == "com.samsung.shealth.tracker.heart_rate":
            self._heart_rate(rows, scan)
        elif stem == "com.samsung.shealth.stress":
            self._stress(rows, scan)
        elif stem == "com.samsung.shealth.sleep":
            self._sleep(rows, scan)
        elif stem == "com.samsung.shealth.exercise":
            self._exercise(rows, scan)
        elif stem == "com.samsung.health.weight":
            self._weight(rows, scan)
        elif stem == "com.samsung.health.respiratory_rate":
            self._respiratory(rows, scan)
        elif stem in {
            "com.samsung.health.height",
            "com.samsung.health.hrv",
            "com.samsung.health.floors_climbed",
            "com.samsung.shealth.tracker.floors_day_summary",
            "com.samsung.health.sleep_stage",
            "com.samsung.health.user_profile",
            "com.samsung.health.device_profile",
        }:
            scan.ignored.append(path.name)
        else:
            scan.ignored.append(path.name)

    def _steps(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        daily: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"value": 0.0, "offset": None, "moment": None}
        )
        for row in rows:
            moment = _parse_time(
                row.get("com.samsung.health.step_count.start_time"),
                row.get("com.samsung.health.step_count.time_offset"),
            )
            count = _number(row.get("com.samsung.health.step_count.count"))
            if moment is None or count is None or count < 0:
                continue
            key = moment.date().isoformat()
            entry = daily[key]
            entry["value"] += count
            entry["offset"] = row.get("com.samsung.health.step_count.time_offset")
            entry["moment"] = moment
        for key, entry in daily.items():
            moment = entry["moment"]
            start = datetime.combine(moment.date(), datetime.min.time(), tzinfo=moment.tzinfo)
            end = start + timedelta(days=1)
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["steps"],
                    kind="steps",
                    captured_at=start.astimezone(UTC),
                    external_id=f"samsung:steps:{key}",
                    unit="count",
                    duration_sec=86400.0,
                    source_app=_source_app(),
                    payload={
                        "value": _tidy(entry["value"]),
                        "unit": "count",
                        "startAt": _iso(start),
                        "endAt": _iso(end),
                        "sourceApp": _source_app(),
                    },
                )
            )

    def _heart_rate(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(
                row.get("com.samsung.health.heart_rate.start_time"),
                row.get("com.samsung.health.heart_rate.time_offset"),
            )
            end = _parse_time(
                row.get("com.samsung.health.heart_rate.end_time"),
                row.get("com.samsung.health.heart_rate.time_offset"),
            )
            value = _number(row.get("com.samsung.health.heart_rate.heart_rate"))
            low = _number(row.get("com.samsung.health.heart_rate.min"))
            high = _number(row.get("com.samsung.health.heart_rate.max"))
            if value is None and low is not None and high is not None:
                value = (low + high) / 2
            if start is None or value is None or not 20 <= value <= 300:
                continue
            payload = {
                "value": _tidy(value),
                "unit": "count/min",
                "startAt": _iso(start),
                "endAt": _iso(end),
                "sourceApp": _source_app(),
            }
            if low is not None:
                payload["min"] = _tidy(low)
            if high is not None:
                payload["max"] = _tidy(high)
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["heart-rate"],
                    kind="heart-rate",
                    captured_at=start.astimezone(UTC),
                    external_id=_external(
                        "hr", row.get("com.samsung.health.heart_rate.datauuid"), _iso(start)
                    ),
                    unit="count/min",
                    duration_sec=(
                        max(0.0, (end - start).total_seconds()) if end else None
                    ),
                    source_app=_source_app(),
                    payload=payload,
                )
            )

    def _stress(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(row.get("start_time"), row.get("time_offset"))
            end = _parse_time(row.get("end_time"), row.get("time_offset"))
            score = _number(row.get("score"))
            if start is None or score is None or not 0 <= score <= 100:
                continue
            payload = {
                "value": _tidy(score),
                "unit": "1",
                "startAt": _iso(start),
                "endAt": _iso(end),
                "sourceApp": _source_app(),
            }
            low, high = _number(row.get("min")), _number(row.get("max"))
            if low is not None:
                payload["min"] = _tidy(low)
            if high is not None:
                payload["max"] = _tidy(high)
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["stress"],
                    kind="stress",
                    captured_at=start.astimezone(UTC),
                    external_id=_external("stress", row.get("datauuid"), _iso(start)),
                    unit="1",
                    duration_sec=(
                        max(0.0, (end - start).total_seconds()) if end else None
                    ),
                    source_app=_source_app(),
                    payload=payload,
                )
            )

    def _sleep(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(
                row.get("com.samsung.health.sleep.start_time"),
                row.get("com.samsung.health.sleep.time_offset"),
            )
            end = _parse_time(
                row.get("com.samsung.health.sleep.end_time"),
                row.get("com.samsung.health.sleep.time_offset"),
            )
            duration_minutes = _number(row.get("sleep_duration"))
            if start is None or end is None:
                continue
            # Samsung 的 sleep_duration 单位是分钟；优先用 start/end 计算。
            seconds = (end - start).total_seconds()
            if seconds <= 0 and duration_minutes is not None and duration_minutes > 0:
                seconds = duration_minutes * 60
            if seconds <= 0 or seconds > 36 * 3600:
                continue
            payload = {
                "value": "asleep",
                "unit": "1",
                "startAt": _iso(start),
                "endAt": _iso(end),
                "sourceApp": _source_app(),
            }
            score = _number(row.get("sleep_score"))
            if score is not None:
                payload["score"] = _tidy(score)
            efficiency = _number(row.get("efficiency"))
            if efficiency is not None:
                payload["efficiency"] = _tidy(efficiency)
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["sleep"],
                    kind="sleep",
                    captured_at=start.astimezone(UTC),
                    external_id=_external(
                        "sleep", row.get("com.samsung.health.sleep.datauuid"), _iso(start)
                    ),
                    unit="1",
                    duration_sec=seconds,
                    source_app=_source_app(),
                    payload=payload,
                    metadata={"sleepCategory": "asleep"},
                )
            )

    def _exercise(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(
                row.get("com.samsung.health.exercise.start_time"),
                row.get("com.samsung.health.exercise.time_offset"),
            )
            end = _parse_time(
                row.get("com.samsung.health.exercise.end_time"),
                row.get("com.samsung.health.exercise.time_offset"),
            )
            if start is None:
                continue
            duration_ms = _number(row.get("com.samsung.health.exercise.duration"))
            seconds = (
                duration_ms / 1000
                if duration_ms is not None and duration_ms > 0
                else ((end - start).total_seconds() if end else None)
            )
            if not seconds or seconds <= 0:
                continue
            raw_type = str(
                row.get("com.samsung.health.exercise.exercise_type")
                or row.get("activity_type")
                or ""
            ).strip()
            activity = ACTIVITY_TYPES.get(raw_type, f"samsung:{raw_type}" if raw_type else "exercise")
            workout = {
                "activity": activity,
                "durationSec": _tidy(seconds),
                "distanceM": _tidy(_number(row.get("com.samsung.health.exercise.distance")) or 0.0) or None,
                "energyKcal": _tidy(_number(row.get("com.samsung.health.exercise.calorie")) or 0.0) or None,
                "avgHeartRate": _tidy(
                    _number(row.get("com.samsung.health.exercise.mean_heart_rate")) or 0.0
                )
                or None,
            }
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["workout"],
                    kind="workout",
                    captured_at=start.astimezone(UTC),
                    external_id=_external(
                        "exercise",
                        row.get("com.samsung.health.exercise.datauuid"),
                        _iso(start),
                    ),
                    unit="1",
                    duration_sec=seconds,
                    source_app=_source_app(),
                    payload={
                        "value": workout,
                        "unit": "1",
                        "startAt": _iso(start),
                        "endAt": _iso(end),
                        "sourceApp": _source_app(),
                    },
                )
            )

    def _weight(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(row.get("start_time"), row.get("time_offset"))
            weight = _number(row.get("weight"))
            if start is None or weight is None or not 20 <= weight <= 400:
                continue
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["body-mass"],
                    kind="body-mass",
                    captured_at=start.astimezone(UTC),
                    external_id=_external("weight", row.get("datauuid"), _iso(start)),
                    unit="kg",
                    source_app=_source_app(),
                    payload={
                        "value": _tidy(weight),
                        "unit": "kg",
                        "startAt": _iso(start),
                        "sourceApp": _source_app(),
                    },
                )
            )

    def _respiratory(self, rows: list[dict[str, str]], scan: _Scan) -> None:
        for row in rows:
            start = _parse_time(row.get("start_time"), row.get("time_offset"))
            end = _parse_time(row.get("end_time"), row.get("time_offset"))
            value = _number(row.get("average"))
            if start is None or value is None or not 4 <= value <= 60:
                continue
            scan.add(
                HealthRecordDraft(
                    record_type=KIND_RECORD_TYPES["respiratory-rate"],
                    kind="respiratory-rate",
                    captured_at=start.astimezone(UTC),
                    external_id=_external("resp", row.get("datauuid"), _iso(start)),
                    unit="count/min",
                    duration_sec=(
                        max(0.0, (end - start).total_seconds()) if end else None
                    ),
                    source_app=_source_app(),
                    payload={
                        "value": _tidy(value),
                        "unit": "count/min",
                        "startAt": _iso(start),
                        "endAt": _iso(end),
                        "sourceApp": _source_app(),
                    },
                )
            )

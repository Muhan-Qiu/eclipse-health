"""小米运动（Mi Fitness）导出 CSV 适配器。

官方导出是 AES 加密 ZIP，应用不解密；用户自行解压后上传明文
``hlth_center_fitness_data.csv``（列 ``Key,Time,Value``，Value 为 JSON）。
支持步数、心率、睡眠、体重；未知 Key 与无法解析的 Value 逐条跳过并计数。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections.abc import Iterable
from datetime import UTC, datetime
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
from .tabular import compact, load_text

FITNESS_FILE_TOKENS = (
    "hlthcenterfitnessdata",
    "hlthcenter",
    "mifitness",
    "xiaomi",
    "mifit",
)
DEFAULT_APP = "Mi Fitness"

KIND_RECORD_TYPES = {
    "steps": "org.eclipsehealth.health.steps",
    "heart-rate": "org.eclipsehealth.health.heart-rate",
    "sleep": "org.eclipsehealth.health.sleep",
    "body-mass": "org.eclipsehealth.health.body-mass",
}

COUNT_KEYS = {
    "steps": "steps",
    "heart-rate": "heartRate",
    "sleep": "sleep",
    "body-mass": "bodyMass",
}

KEY_KINDS = {
    "steps": "steps",
    "step": "steps",
    "stepcount": "steps",
    "stepsvalue": "steps",
    "heartrate": "heart-rate",
    "hr": "heart-rate",
    "heartratevalue": "heart-rate",
    "heartrateavg": "heart-rate",
    "sleep": "sleep",
    "sleepdetail": "sleep",
    "sleepdata": "sleep",
    "sleepinfo": "sleep",
    "sleepstage": "sleep",
    "sleepduration": "sleep",
    "weight": "body-mass",
    "bodyweight": "body-mass",
    "bodymass": "body-mass",
    "weightvalue": "body-mass",
}

VALUE_KEYS = {
    "steps": ("steps", "step", "stepcount", "count", "value"),
    "heart-rate": ("heart_rate", "heartrate", "hr", "rate", "value", "avg"),
    "body-mass": ("weight", "body_weight", "bodyweight", "value"),
    "sleep": ("duration", "sleep_duration", "minutes", "value"),
}

START_KEYS = ("startTime", "start_time", "sleep_start", "begin", "start", "from")
END_KEYS = ("endTime", "end_time", "sleep_end", "end", "to")
STAGE_KEYS = ("stage", "sleep_stage", "sleepStage", "level")

_UNIT_BY_KIND = {
    "steps": "count",
    "heart-rate": "count/min",
    "body-mass": "kg",
    "sleep": "min",
}


def _fingerprint(*parts: Any) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _tidy(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(value, 6)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        moment = float(value)
        if moment > 1e15:
            moment /= 1_000_000.0
        elif moment > 1e12:
            moment /= 1_000.0
        try:
            return datetime.fromtimestamp(moment, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return _parse_time(float(text))
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


class XiaomiAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.xiaomi"
    adapter_version = "1.0.0"
    format = "xiaomi"

    # ---------------------------------------------------------------- detect
    def detect(self, source: ImportSource) -> Detection | None:
        name = compact(source.original_name or source.path.name)
        marked_name = any(token in name for token in FITNESS_FILE_TOKENS)
        if source.encrypted:
            return (
                Detection(self.format, 0.98, "小米导出包（加密 ZIP）")
                if marked_name
                else None
            )
        path = self._pick_file(source, missing_ok=True)
        if path is None:
            return None
        if marked_name:
            return Detection(self.format, 0.96, "文件名像小米运动导出")
        if self._has_fitness_header(path):
            return Detection(self.format, 0.98, "表头为 Key,Time,Value")
        return None

    def _pick_file(self, source: ImportSource, *, missing_ok: bool) -> Path | None:
        candidates: list[Path] = []
        if source.extracted_dir is not None:
            candidates = sorted(
                path
                for path in source.extracted_dir.rglob("*")
                if path.is_file() and path.suffix.lower() == ".csv"
            )
        elif source.path.is_file() and source.path.suffix.lower() == ".csv":
            candidates = [source.path]
        elif source.path.is_dir():
            candidates = sorted(
                path
                for path in source.path.rglob("*")
                if path.is_file() and path.suffix.lower() == ".csv"
            )
        if not candidates:
            if missing_ok:
                return None
            raise invalid_file("未找到小米运动 CSV", code="unsupported_xiaomi_export")
        preferred = [
            path
            for path in candidates
            if any(token in compact(path.name) for token in FITNESS_FILE_TOKENS)
        ]
        return (preferred or candidates)[0]

    @staticmethod
    def _has_fitness_header(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                head = handle.read(4096).decode("utf-8-sig", errors="replace")
        except OSError:
            return False
        first = next((line for line in head.splitlines() if line.strip()), "")
        try:
            row = next(csv.reader([first]))
        except csv.Error:
            return False
        return [compact(cell) for cell in row[:3]] == ["key", "time", "value"]

    # ----------------------------------------------------------------- build
    def _build(self, source: ImportSource) -> ParsedImport:
        if source.encrypted:
            raise invalid_file(
                "这个小米导出 ZIP 已加密。请先按邮件里的密码解压，"
                "再上传其中的 hlth_center_fitness_data.csv",
                code="encrypted_export",
            )
        path = self._pick_file(source, missing_ok=False)
        assert path is not None
        text, _, text_warnings = load_text(path)
        reader = csv.reader(io.StringIO(text))
        rows = _non_empty(reader)
        try:
            header = next(rows)
        except StopIteration:
            raise invalid_file(
                "小米 CSV 是空文件", code="unsupported_xiaomi_export"
            ) from None

        tokens = [compact(cell) for cell in header]
        try:
            key_index = tokens.index("key")
            time_index = tokens.index("time")
            value_index = tokens.index("value")
        except ValueError:
            raise invalid_file(
                "这不是小米运动导出：需要 Key,Time,Value 三列表头",
                code="unsupported_xiaomi_export",
                details={"headers": [cell[:32] for cell in header[:8]]},
            ) from None

        drafts: list[HealthRecordDraft] = []
        counts: dict[str, int] = {}
        ignored = 0
        invalid = 0
        warnings = list(text_warnings)
        for row in rows:
            if max(key_index, time_index, value_index) >= len(row):
                invalid += 1
                continue
            key = row[key_index].strip()
            kind = KEY_KINDS.get(compact(key))
            if kind is None:
                ignored += 1
                continue
            try:
                payload = json.loads(row[value_index])
            except ValueError:
                invalid += 1
                continue
            draft = self._draft(kind, key, row[time_index], payload)
            if draft is None:
                invalid += 1
                continue
            drafts.append(draft)
            count_key = COUNT_KEYS.get(kind, kind)
            counts[count_key] = counts.get(count_key, 0) + 1
            if len(drafts) > limits.HEALTH_MAX_RECORDS:
                raise invalid_file(
                    f"记录数超过 {limits.HEALTH_MAX_RECORDS} 条上限，请缩小导出时间范围",
                    code="import_too_many_records",
                    details={"limit": limits.HEALTH_MAX_RECORDS},
                )

        if not drafts:
            raise invalid_file(
                "小米 CSV 里没有可导入的步数/心率/睡眠/体重数据",
                code="unsupported_xiaomi_export",
                details={"ignoredKeys": ignored, "invalidRows": invalid},
            )

        if ignored:
            warnings.append(
                warning(
                    "xiaomi_ignored_keys",
                    f"已跳过 {ignored} 行未映射的 Key",
                    severity="info",
                )
            )
        if invalid:
            warnings.append(
                warning(
                    "xiaomi_invalid_rows",
                    f"已跳过 {invalid} 行无法解析的数值",
                    severity="warning",
                )
            )
        if len(drafts) > limits.HEALTH_LARGE_RECORDS:
            warnings.append(
                warning(
                    "large_import",
                    f"本次将导入 {len(drafts)} 条记录，提交可能需要几分钟",
                    severity="warning",
                )
            )
        warnings.append(
            warning(
                "xiaomi_fitness_imported",
                f"小米运动导出：{len(drafts)} 条健康记录",
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
            metadata={"importSource": "xiaomi-mi-fitness", "format": self.format},
            warnings=warnings,
            health_records=drafts,
            record_counts=counts,
            total_records=len(drafts),
            import_source="xiaomi-mi-fitness",
        )

    def _draft(
        self, kind: str, key: str, raw_time: str, payload: Any
    ) -> HealthRecordDraft | None:
        row_time = _parse_time(raw_time)
        if row_time is None:
            return None

        if isinstance(payload, list):
            # 社区导出里心率/睡眠偶尔是列表；无法可靠拆成独立时间段时跳过。
            return None
        if isinstance(payload, dict):
            value = _first_number(payload, VALUE_KEYS[kind])
            start = _first_time(payload, START_KEYS) or row_time
            end = _first_time(payload, END_KEYS)
            stage = _first_text(payload, STAGE_KEYS)
            if kind == "sleep" and value is None and stage is not None:
                return self._sleep_stage_draft(key, payload, start, end, stage)
            if value is None:
                return None
            return self._make_draft(kind, key, value, start, end, payload)
        value = _number(payload)
        if value is None:
            return None
        return self._make_draft(kind, key, value, row_time, None, payload)

    def _make_draft(
        self,
        kind: str,
        key: str,
        value: float,
        start: datetime,
        end: datetime | None,
        raw_payload: Any,
    ) -> HealthRecordDraft | None:
        unit = _UNIT_BY_KIND[kind]
        duration = max(0.0, (end - start).total_seconds()) if end else None
        if kind == "sleep" and duration is None:
            # 小米睡眠的数值通常为分钟。
            duration = value * 60.0
        return HealthRecordDraft(
            record_type=KIND_RECORD_TYPES[kind],
            kind=kind,
            captured_at=start,
            external_id=f"xiaomi:{_fingerprint(key, start.isoformat(), raw_payload)}",
            unit=unit,
            source_app=DEFAULT_APP,
            duration_sec=duration,
            payload={
                "value": _tidy(value),
                "unit": unit,
                "startAt": start.isoformat(),
                "endAt": end.isoformat() if end else None,
                "sourceApp": DEFAULT_APP,
            },
            metadata={"xiaomiKey": key},
        )

    def _sleep_stage_draft(
        self,
        key: str,
        payload: dict[str, Any],
        start: datetime,
        end: datetime | None,
        stage: str,
    ) -> HealthRecordDraft:
        duration = max(0.0, (end - start).total_seconds()) if end else None
        return HealthRecordDraft(
            record_type=KIND_RECORD_TYPES["sleep"],
            kind="sleep",
            captured_at=start,
            external_id=f"xiaomi:{_fingerprint(key, start.isoformat(), payload)}",
            unit="1",
            source_app=DEFAULT_APP,
            duration_sec=duration,
            payload={
                "value": stage.lower()[:32],
                "unit": "1",
                "startAt": start.isoformat(),
                "endAt": end.isoformat() if end else None,
                "sourceApp": DEFAULT_APP,
            },
            metadata={"xiaomiKey": key},
        )

    # --------------------------------------------------------------- adapters
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


def _non_empty(reader: Iterable[list[str]]) -> Iterable[list[str]]:
    for row in reader:
        if any(cell.strip() for cell in row):
            yield row


def _first_number(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in payload:
            value = _number(payload[key])
            if value is not None:
                return value
    # 键名大小写/下划线差异兜底。
    lowered = {compact(name): value for name, value in payload.items()}
    for key in keys:
        value = _number(lowered.get(compact(key)))
        if value is not None:
            return value
    return None


def _first_time(payload: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        if key in payload:
            parsed = _parse_time(payload[key])
            if parsed is not None:
                return parsed
    lowered = {compact(name): value for name, value in payload.items()}
    for key in keys:
        parsed = _parse_time(lowered.get(compact(key)))
        if parsed is not None:
            return parsed
    return None


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = ["XiaomiAdapter"]

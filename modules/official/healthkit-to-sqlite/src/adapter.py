"""Apple Health ``export.xml`` / ``export.zip`` 的 stdlib 流式解析。

只复用 healthkit-to-sqlite 的字段映射思路，不依赖 sqlite-utils：
zipfile + xml.etree.ElementTree.iterparse。丢弃 sourceName/device 等设备标识，
不保留文件路径，避免把可识别信息带进记录。
"""

from __future__ import annotations

import math
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAX_RECORDS_DEFAULT = 100_000
_MAX_VALUE_LEN = 64

# Apple Health type -> (recordType, metric)
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "HKQuantityTypeIdentifierHeartRate": ("vital.measurement", "heart_rate"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("vital.measurement", "resting_heart_rate"),
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": ("vital.measurement", "walking_heart_rate"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("vital.measurement", "hrv_sdnn"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("vital.measurement", "oxygen_saturation"),
    "HKQuantityTypeIdentifierBodyTemperature": ("vital.measurement", "body_temperature"),
    "HKQuantityTypeIdentifierBloodPressureSystolic": ("vital.measurement", "blood_pressure_systolic"),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": ("vital.measurement", "blood_pressure_diastolic"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("vital.measurement", "respiratory_rate"),
    "HKQuantityTypeIdentifierBodyMass": ("vital.measurement", "body_weight"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("vital.measurement", "body_fat_percentage"),
    "HKQuantityTypeIdentifierLeanBodyMass": ("vital.measurement", "lean_body_mass"),
    "HKQuantityTypeIdentifierStepCount": ("activity.sample", "steps"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("activity.sample", "distance_walking_running"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("activity.sample", "active_energy"),
    "HKQuantityTypeIdentifierFlightsClimbed": ("activity.sample", "flights_climbed"),
    "HKCategoryTypeIdentifierSleepAnalysis": ("sleep.session", "sleep_analysis"),
}


class HealthExportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def map_record_type(hk_type: Any) -> tuple[str, str]:
    text = str(hk_type or "")
    if text in _TYPE_MAP:
        return _TYPE_MAP[text]
    if text.startswith("HKCategoryTypeIdentifierSleepAnalysis"):
        return ("sleep.session", "sleep_analysis")
    return ("vital.measurement", "unknown")


def _coerce(value: Any) -> float | str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text[:_MAX_VALUE_LEN]
    return number if math.isfinite(number) else text[:_MAX_VALUE_LEN]


def parse_record(attributes: dict[str, Any]) -> dict[str, Any]:
    """把 ``<Record .../>`` 属性映射为记录 payload。"""
    hk_type = attributes.get("type")
    if not hk_type:
        raise HealthExportError("invalid_record", "Record 缺少 type")
    record_type, metric = map_record_type(hk_type)
    start = str(attributes.get("startDate") or "")
    if not start:
        raise HealthExportError("invalid_record", "Record 缺少 startDate")
    payload: dict[str, Any] = {
        "metric": metric,
        "unit": str(attributes.get("unit") or "")[:32],
        "start": start,
        "end": str(attributes.get("endDate") or start),
        "value": _coerce(attributes.get("value")),
    }
    return {"recordType": record_type, "payload": payload}


def parse_workout(attributes: dict[str, Any]) -> dict[str, Any]:
    activity_type = str(attributes.get("workoutActivityType") or "workout")
    start = str(attributes.get("startDate") or "")
    end = str(attributes.get("endDate") or start)
    if not start:
        raise HealthExportError("invalid_record", "Workout 缺少 startDate")
    duration = _coerce(attributes.get("duration"))
    payload: dict[str, Any] = {
        "activityType": activity_type[:64],
        "start": start,
        "end": end,
        "durationSeconds": duration if isinstance(duration, float) else 0.0,
    }
    energy = _coerce(attributes.get("totalEnergyBurned"))
    distance = _coerce(attributes.get("totalDistance"))
    if isinstance(energy, float):
        payload["energyKcal"] = energy
    if isinstance(distance, float):
        payload["distanceKm"] = distance
    return {"recordType": "activity.workout", "payload": payload}


def iter_records(file_obj: Any, limit: int = MAX_RECORDS_DEFAULT) -> Iterator[dict[str, Any]]:
    """流式产出记录；达到 limit 即停止（调用方据此标记 truncated）。"""
    count = 0
    for _, element in ET.iterparse(file_obj, events=("end",)):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"Record", "Workout"}:
            continue
        try:
            item = parse_workout(element.attrib) if tag == "Workout" else parse_record(element.attrib)
        except HealthExportError:
            item = None
        element.clear()
        if item is None:
            continue
        yield item
        count += 1
        if count >= limit:
            return


def _open_xml(path: Path) -> Any:
    if path.suffix.lower() == ".zip":
        archive = zipfile.ZipFile(path)
        candidates = [
            name
            for name in archive.namelist()
            if name == "export.xml" or name.endswith("/export.xml")
        ]
        if not candidates:
            archive.close()
            raise HealthExportError("missing_export_xml", "压缩包内未找到 export.xml")
        return archive.open(candidates[0], "r")
    if path.suffix.lower() == ".xml":
        return path.open("rb")
    raise HealthExportError("unsupported_file", "仅支持 export.zip 或 export.xml")


def read_export(path: str | Path, limit: int = MAX_RECORDS_DEFAULT) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise HealthExportError("invalid_path", "导入路径不是可读文件")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200_000:
        raise HealthExportError("invalid_limit", "limit 必须是 1..200000 的整数")
    records: list[dict[str, Any]] = []
    truncated = False
    handle = _open_xml(target)
    try:
        records = list(iter_records(handle, limit + 1))
        if len(records) > limit:
            truncated = True
            records = records[:limit]
    except ET.ParseError as exc:
        raise HealthExportError("invalid_xml", "export.xml 解析失败") from exc
    finally:
        handle.close()
    return {
        "records": records,
        "count": len(records),
        "truncated": truncated,
        "counts": summarize(records),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        record_type = str(item.get("recordType") or "unknown")
        counts[record_type] = counts.get(record_type, 0) + 1
    return dict(sorted(counts.items()))

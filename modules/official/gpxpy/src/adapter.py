"""GPX 轨迹解析/生成与统计（纯 stdlib 实现，便于单测）。"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import datetime
from itertools import pairwise
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

_EARTH_RADIUS_M = 6_371_000.0
_MAX_HEART_RATE = 300


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_gpx_xml(text: str) -> list[dict[str, Any]]:
    """用 stdlib 解析 GPX trkpt；命名空间无关，忽略非法坐标点。"""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("GPX 内容为空")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("GPX 不是合法 XML") from exc
    if _local(root.tag) != "gpx":
        raise ValueError("根元素不是 gpx")
    points: list[dict[str, Any]] = []
    for element in root.iter():
        if _local(element.tag) != "trkpt":
            continue
        latitude = _float(element.attrib.get("lat"))
        longitude = _float(element.attrib.get("lon"))
        if latitude is None or longitude is None:
            continue
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        elevation = None
        timestamp = None
        heart_rate = None
        for child in element.iter():
            name = _local(child.tag)
            if name == "ele":
                elevation = _float(child.text)
            elif name == "time":
                timestamp = _iso(child.text)
            elif name in {"hr", "heartrate"}:
                value = _float(child.text)
                if value is not None and 20 <= value <= _MAX_HEART_RATE:
                    heart_rate = int(value)
        points.append(
            {
                "lat": latitude,
                "lon": longitude,
                "ele": elevation,
                "time": timestamp,
                "heartRate": heart_rate,
            }
        )
    if not points:
        raise ValueError("GPX 中没有有效轨迹点")
    return points


def haversine_m(first: dict[str, Any], second: dict[str, Any]) -> float:
    lat1 = math.radians(float(first["lat"]))
    lat2 = math.radians(float(second["lat"]))
    delta_lat = lat2 - lat1
    delta_lon = math.radians(float(second["lon"]) - float(first["lon"]))
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(value)))


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        first = datetime.fromisoformat(start)
        last = datetime.fromisoformat(end)
        seconds = (last - first).total_seconds()
    except (TypeError, ValueError):
        return None
    return round(seconds, 3) if seconds >= 0 else None


def summarize_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(points, list) or not points:
        raise ValueError("没有可用的 GPX 轨迹点")
    distance = sum(
        haversine_m(first, second) for first, second in pairwise(points)
    )
    elevations = [item["ele"] for item in points if item.get("ele") is not None]
    gain = sum(max(0.0, second - first) for first, second in pairwise(elevations))
    loss = sum(max(0.0, first - second) for first, second in pairwise(elevations))
    heart_rates = [item["heartRate"] for item in points if item.get("heartRate") is not None]
    timestamps = [item["time"] for item in points if item.get("time")]
    duration = _duration_seconds(
        timestamps[0] if timestamps else None,
        timestamps[-1] if timestamps else None,
    )
    speed_kph = None
    if duration and distance:
        speed_kph = round(distance / 1000.0 / (duration / 3600.0), 2)
    return {
        "samples": len(points),
        "startedAt": timestamps[0] if timestamps else None,
        "endedAt": timestamps[-1] if timestamps else None,
        "durationSeconds": duration,
        "distanceKm": round(distance / 1000.0, 3),
        "elevationGainM": round(gain, 1),
        "elevationLossM": round(loss, 1),
        "avgSpeedKph": speed_kph,
        "avgHeartRate": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
        "maxHeartRate": max(heart_rates) if heart_rates else None,
        "heartRateCoverage": round(len(heart_rates) / len(points), 3),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def session_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "startedAt": summary.get("startedAt"),
        "endedAt": summary.get("endedAt"),
        "durationSeconds": summary.get("durationSeconds"),
        "distanceKm": summary.get("distanceKm"),
        "elevationGainM": summary.get("elevationGainM"),
        "elevationLossM": summary.get("elevationLossM"),
        "avgHeartRate": summary.get("avgHeartRate"),
        "maxHeartRate": summary.get("maxHeartRate"),
        "source": "gpx",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def to_gpx(points: list[dict[str, Any]], name: str = "eclipse health export") -> str:
    """生成 GPX 1.1；缺 lat/lon 的点直接拒绝。"""
    if not isinstance(points, list) or not points:
        raise ValueError("没有可导出的轨迹点")
    root = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "eclipse health",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )
    track = ET.SubElement(root, "trk")
    ET.SubElement(track, "name").text = str(name)[:120]
    segment = ET.SubElement(track, "trkseg")
    for point in points:
        latitude = _float(point.get("lat")) if isinstance(point, dict) else None
        longitude = _float(point.get("lon")) if isinstance(point, dict) else None
        if latitude is None or longitude is None:
            raise ValueError("轨迹点缺少有效的 lat/lon")
        element = ET.SubElement(
            segment, "trkpt", {"lat": f"{latitude:.7f}", "lon": f"{longitude:.7f}"}
        )
        elevation = _float(point.get("ele"))
        if elevation is not None:
            ET.SubElement(element, "ele").text = f"{elevation:.2f}"
        timestamp = _iso(point.get("time"))
        if timestamp:
            ET.SubElement(element, "time").text = timestamp
        heart_rate = _float(point.get("heartRate"))
        if heart_rate is not None and 20 <= heart_rate <= _MAX_HEART_RATE:
            extensions = ET.SubElement(element, "extensions")
            ET.SubElement(extensions, "hr").text = str(int(heart_rate))
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")

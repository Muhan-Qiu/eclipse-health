"""BLE GATT 解析（纯函数）。按 Bluetooth SIG 心率/体重测量特征解析字节。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

_MAX_HEART_RATE = 300
_LB_TO_KG = 0.45359237


def _require_bytes(data: Any, minimum: int) -> bytes:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("BLE 数据必须是 bytes")
    raw = bytes(data)
    if len(raw) < minimum:
        raise ValueError(f"BLE 数据至少 {minimum} 字节")
    return raw


def parse_heart_rate_measurement(data: bytes) -> dict[str, Any]:
    """Heart Rate Measurement (0x2A37)。"""
    raw = _require_bytes(data, 2)
    flags = raw[0]
    offset = 1
    if flags & 0x01:
        if len(raw) < offset + 2:
            raise ValueError("心率测量缺少 uint16 值")
        heart_rate = int.from_bytes(raw[offset : offset + 2], "little")
        offset += 2
    else:
        heart_rate = raw[offset]
        offset += 1
    if not 20 <= heart_rate <= _MAX_HEART_RATE:
        raise ValueError("心率值超出 20..300")
    contact: bool | None = None
    if flags & 0x04:
        contact = bool(flags & 0x02)
    energy = None
    if flags & 0x08:
        if len(raw) < offset + 2:
            raise ValueError("心率测量缺少能量消耗字段")
        energy = int.from_bytes(raw[offset : offset + 2], "little")
        offset += 2
    rr_intervals: list[float] = []
    while offset + 2 <= len(raw):
        ticks = int.from_bytes(raw[offset : offset + 2], "little")
        rr_intervals.append(round(ticks * 1000.0 / 1024.0, 2))
        offset += 2
    return {
        "heartRate": heart_rate,
        "sensorContact": contact,
        "energyExpended": energy,
        "rrIntervalsMs": rr_intervals,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def _ble_datetime(raw: bytes, offset: int) -> str | None:
    if len(raw) < offset + 7:
        return None
    try:
        value = datetime(
            int.from_bytes(raw[offset : offset + 2], "little"),
            raw[offset + 2],
            raw[offset + 3],
            raw[offset + 4],
            raw[offset + 5],
            raw[offset + 6],
        )
    except ValueError:
        return None
    return value.isoformat()


def parse_body_composition_measurement(data: bytes) -> dict[str, Any]:
    """Body Composition Measurement (0x2A9C)；按 flags 顺序跳过可选字段。"""
    raw = _require_bytes(data, 4)
    flags = int.from_bytes(raw[0:2], "little")
    imperial = bool(flags & 0x0001)
    offset = 2
    body_fat = int.from_bytes(raw[offset : offset + 2], "little") * 0.1
    offset += 2
    timestamp = None
    if flags & 0x0002:
        timestamp = _ble_datetime(raw, offset)
        offset += 7
    if flags & 0x0004:
        offset += 1
    # 依次为：基础代谢、肌肉率、肌肉量、去脂体重、软瘦体重、体水分量、阻抗。
    for bit in (0x0008, 0x0010, 0x0020, 0x0040, 0x0080, 0x0100, 0x0200):
        if flags & bit:
            offset += 2
    weight = None
    if flags & 0x0400:
        if len(raw) < offset + 2:
            raise ValueError("体成分数据在体重字段处截断")
        value = int.from_bytes(raw[offset : offset + 2], "little")
        weight = round(value * (0.005 if not imperial else 0.01 * _LB_TO_KG), 4)
        offset += 2
    height = None
    if flags & 0x0800:
        if len(raw) < offset + 2:
            raise ValueError("体成分数据在身高字段处截断")
        value = int.from_bytes(raw[offset : offset + 2], "little")
        height = round(value * (0.001 if not imperial else 0.1 * 0.0254), 4)
    return {
        "bodyFatPercent": round(body_fat, 1),
        "weightKg": weight,
        "heightM": height,
        "measuredAt": timestamp,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def summarize_hr_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(samples, list) or not samples:
        raise ValueError("没有心率采样")
    rates = [item["heartRate"] for item in samples if item.get("heartRate") is not None]
    if not rates:
        raise ValueError("没有有效心率值")
    coverage = len(rates) / len(samples)
    return {
        "samples": len(samples),
        "avgHeartRate": round(sum(rates) / len(rates), 1),
        "minHeartRate": min(rates),
        "maxHeartRate": max(rates),
        "coverage": round(coverage, 3),
        "quality": "good" if coverage >= 0.8 else "partial" if coverage >= 0.3 else "poor",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

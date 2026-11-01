"""EDF/BDF 导出/导入的纯函数参数校验。

EDF 规范要求通道标签 ≤16 个 ASCII 字符；本模块在进入 pyedflib 前就把非法值挡掉。
不 import pyedflib/numpy，便于核心 venv 直接单测。
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Any

_LABEL_CLEAN_RE = re.compile(r"[^A-Za-z0-9 _+.-]+")
_MAX_SAMPLES = 4_000_000


class EdfAdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sanitize_label(label: Any, fallback: str) -> str:
    cleaned = _LABEL_CLEAN_RE.sub("", str(label or "")).strip()[:16]
    return cleaned or fallback[:16]


def parse_start_date(value: Any) -> str:
    """接受 ``YYYY-MM-DD`` 或 ``YYYY-MM-DDTHH:MM:SS``，返回 pyedflib 需要的时间串。"""
    text = str(value or "").strip()
    if not text:
        return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise EdfAdapterError("invalid_start_date", "startDate 必须是 ISO 时间") from exc
    return parsed.replace(microsecond=0).isoformat(sep=" ")


def _channels(value: Any) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise EdfAdapterError("invalid_channels", "channels 必须是非空数组")
    result: list[list[float]] = []
    for index, channel in enumerate(value):
        if not isinstance(channel, (list, tuple)) or not channel:
            raise EdfAdapterError("invalid_channels", f"通道 {index} 必须是非空数组")
        if len(channel) > _MAX_SAMPLES:
            raise EdfAdapterError("too_many_samples", f"通道 {index} 超过 {_MAX_SAMPLES} 个样本")
        row: list[float] = []
        for sample in channel:
            if isinstance(sample, bool) or not isinstance(sample, (int, float)):
                raise EdfAdapterError("invalid_channels", f"通道 {index} 含非数值样本")
            number = float(sample)
            if not math.isfinite(number):
                raise EdfAdapterError("invalid_channels", f"通道 {index} 含 NaN/Inf")
            row.append(number)
        result.append(row)
    if len({len(row) for row in result}) != 1:
        raise EdfAdapterError("channel_length_mismatch", "所有通道长度必须一致")
    return result


def build_edf_plan(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise EdfAdapterError("invalid_input", "params 必须是对象")
    try:
        fs = float(params.get("fs"))
    except (TypeError, ValueError) as exc:
        raise EdfAdapterError("invalid_fs", "fs 必须是数字") from exc
    if not math.isfinite(fs) or not 1 <= fs <= 100_000:
        raise EdfAdapterError("invalid_fs", "fs 必须在 1..100000 Hz")
    channels = _channels(params.get("channels"))
    count = len(channels)
    raw_labels = params.get("labels")
    if raw_labels is None:
        labels = [f"ch{index + 1}" for index in range(count)]
    elif isinstance(raw_labels, list) and len(raw_labels) == count:
        labels = [sanitize_label(item, f"ch{index + 1}") for index, item in enumerate(raw_labels)]
    else:
        raise EdfAdapterError("invalid_labels", "labels 必须与通道数一致")
    raw_units = params.get("units")
    if raw_units is None:
        units = ["uV"] * count
    elif isinstance(raw_units, list) and len(raw_units) == count:
        units = [str(item)[:16] for item in raw_units]
    else:
        raise EdfAdapterError("invalid_units", "units 必须与通道数一致")
    try:
        physical_min = float(params.get("physicalMin", -32768.0))
        physical_max = float(params.get("physicalMax", 32767.0))
    except (TypeError, ValueError) as exc:
        raise EdfAdapterError("invalid_range", "physicalMin/physicalMax 必须是数字") from exc
    if not physical_min < physical_max:
        raise EdfAdapterError("invalid_range", "physicalMin 必须小于 physicalMax")
    return {
        "fs": fs,
        "channels": channels,
        "labels": labels,
        "units": units,
        "physicalMin": physical_min,
        "physicalMax": physical_max,
        "digitalMin": -32768,
        "digitalMax": 32767,
        "startDate": parse_start_date(params.get("startDate")),
        "recordName": sanitize_label(params.get("recordName") or "record", "record"),
    }


def to_csv_text(labels: list[str], channels: list[list[float]], fs: float, max_rows: int = 200_000) -> str:
    if not channels or not labels or len(labels) != len(channels):
        raise EdfAdapterError("invalid_channels", "CSV 导出的标签与通道不一致")
    rows = min(len(channels[0]), max_rows)
    lines = [",".join(["time_s", *labels])]
    for index in range(rows):
        values = [f"{index / fs:.6f}"]
        values.extend(f"{channel[index]:.9g}" for channel in channels)
        lines.append(",".join(values))
    return "\n".join(lines) + "\n"


def summarize_import(labels: list[Any], fs: Any, n_samples: int) -> dict[str, Any]:
    if n_samples <= 0:
        raise EdfAdapterError("empty_record", "EDF/BDF 记录不含样本")
    try:
        sampling = float(fs)
    except (TypeError, ValueError) as exc:
        raise EdfAdapterError("invalid_fs", "记录采样率非法") from exc
    return {
        "labels": [str(item) for item in labels],
        "fs": sampling,
        "nSamples": int(n_samples),
        "channels": len(labels),
        "durationSeconds": round(n_samples / sampling, 3) if sampling > 0 else None,
    }

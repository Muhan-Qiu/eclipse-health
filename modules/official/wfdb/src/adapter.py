"""WFDB 导出/导入的纯函数参数校验与格式化。

不 import wfdb/numpy，便于在核心 venv 直接单测；真正的文件读写在 main.py。
"""

from __future__ import annotations

import math
import re
from typing import Any

_RECORD_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
_SIG_NAME_RE = re.compile(r"[^A-Za-z0-9]+")
_MAX_SAMPLES = 5_000_000


class WfdbAdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sanitize_record_name(name: Any) -> str:
    cleaned = _RECORD_NAME_RE.sub("", str(name or "").strip())[:64]
    if not cleaned:
        raise WfdbAdapterError("invalid_record_name", "recordName 必须包含字母或数字")
    return cleaned


def _as_channels(value: Any) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise WfdbAdapterError("invalid_channels", "channels 必须是非空数组")
    channels: list[list[float]] = []
    for index, channel in enumerate(value):
        if not isinstance(channel, (list, tuple)) or not channel:
            raise WfdbAdapterError("invalid_channels", f"通道 {index} 必须是非空数组")
        if len(channel) > _MAX_SAMPLES:
            raise WfdbAdapterError("too_many_samples", f"通道 {index} 超过 {_MAX_SAMPLES} 个样本")
        converted: list[float] = []
        for sample in channel:
            if isinstance(sample, bool) or not isinstance(sample, (int, float)):
                raise WfdbAdapterError("invalid_channels", f"通道 {index} 含非数值样本")
            number = float(sample)
            if not math.isfinite(number):
                raise WfdbAdapterError("invalid_channels", f"通道 {index} 含 NaN/Inf")
            converted.append(number)
        channels.append(converted)
    lengths = {len(channel) for channel in channels}
    if len(lengths) != 1:
        raise WfdbAdapterError("channel_length_mismatch", "所有通道长度必须一致")
    return channels


def build_export_plan(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise WfdbAdapterError("invalid_input", "params 必须是对象")
    record_name = sanitize_record_name(params.get("recordName") or "record")
    try:
        fs = float(params.get("fs"))
    except (TypeError, ValueError) as exc:
        raise WfdbAdapterError("invalid_fs", "fs 必须是数字") from exc
    if not math.isfinite(fs) or not 1 <= fs <= 100_000:
        raise WfdbAdapterError("invalid_fs", "fs 必须在 1..100000 Hz")
    channels = _as_channels(params.get("channels"))
    count = len(channels)
    raw_names = params.get("sigName")
    if raw_names is None:
        sig_names = [f"ch{index + 1}" for index in range(count)]
    elif isinstance(raw_names, list) and len(raw_names) == count:
        sig_names = []
        for index, item in enumerate(raw_names):
            cleaned = _SIG_NAME_RE.sub("_", str(item)).strip("_")[:20]
            sig_names.append(cleaned or f"ch{index + 1}")
    else:
        raise WfdbAdapterError("invalid_sig_name", "sigName 必须与通道数一致")
    units = params.get("units")
    if units is None:
        units = ["mV"] * count
    elif not isinstance(units, list) or len(units) != count:
        raise WfdbAdapterError("invalid_units", "units 必须与通道数一致")
    comments = params.get("comments")
    if comments is not None and not isinstance(comments, list):
        raise WfdbAdapterError("invalid_comments", "comments 必须是字符串数组")
    return {
        "recordName": record_name,
        "fs": fs,
        "channels": channels,
        "sigName": sig_names,
        "units": [str(item)[:20] for item in units],
        "comments": [str(item)[:255] for item in (comments or [])][:16],
    }


def to_csv_text(labels: list[str], channels: list[list[float]], fs: float, max_rows: int = 200_000) -> str:
    if not channels or not labels or len(labels) != len(channels):
        raise WfdbAdapterError("invalid_channels", "CSV 导出的标签与通道不一致")
    rows = min(len(channels[0]), max_rows)
    lines = [",".join(["time_s", *labels])]
    for index in range(rows):
        values = [f"{index / fs:.6f}"]
        values.extend(f"{channel[index]:.9g}" for channel in channels)
        lines.append(",".join(values))
    return "\n".join(lines) + "\n"


def summarize_import(sig_name: list[Any], units: list[Any], fs: Any, n_samples: int) -> dict[str, Any]:
    if n_samples <= 0:
        raise WfdbAdapterError("empty_record", "WFDB 记录不含样本")
    try:
        sampling = float(fs)
    except (TypeError, ValueError) as exc:
        raise WfdbAdapterError("invalid_fs", "记录采样率非法") from exc
    return {
        "sigName": [str(item) for item in sig_name],
        "units": [str(item) for item in units],
        "fs": sampling,
        "nSamples": int(n_samples),
        "channels": len(sig_name),
        "durationSeconds": round(n_samples / sampling, 3) if sampling > 0 else None,
    }

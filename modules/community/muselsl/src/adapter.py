"""muselsl 适配层：CSV 解析、preset/通道映射、stream 命令构造（纯标准库）。

上游 ``muselsl``/``pylsl`` 只在 ``main.py`` 启动流时通过子进程调用。
"""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "muselsl"
MAX_TEXT_BYTES = 16_000_000
MAX_ROWS = 500_000

PRESETS: dict[str, list[str]] = {
    "muse-2016": ["TP9", "AF7", "AF8", "TP10"],
    "muse-2": ["TP9", "AF7", "AF8", "TP10"],
    "muse-s": ["TP9", "AF7", "AF8", "TP10"],
    "muse-2s": ["TP9", "AF7", "AF8", "TP10"],
}
_TIME_HEADERS = {"timestamp", "timestamps", "time", "lsl_timestamp"}


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def channel_names(preset: Any) -> list[str]:
    if not isinstance(preset, str) or preset not in PRESETS:
        raise AdapterError(f"preset 必须是 {', '.join(sorted(PRESETS))}")
    return list(PRESETS[preset])


def devices_payload() -> dict[str, Any]:
    return {
        "items": [{"preset": name, "channels": channels} for name, channels in PRESETS.items()],
        "note": DISCLAIMER,
    }


def _parse_time(value: str, row_number: int) -> float:
    text = value.strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AdapterError(f"第 {row_number} 行时间戳无法解析") from exc
    return parsed.timestamp()


class _ChannelStats:
    __slots__ = ("clipped", "count", "flat", "maximum", "minimum", "previous", "total", "total_sq")

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.total_sq = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.previous: float | None = None
        self.flat = 0
        self.clipped = 0

    def add(self, value: float, clipping_uv: float) -> None:
        self.count += 1
        self.total += value
        self.total_sq += value * value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        if abs(value) >= clipping_uv:
            self.clipped += 1
        if self.previous is not None and abs(value - self.previous) < 1e-9:
            self.flat += 1
        self.previous = value

    def summary(self, name: str, index: int) -> dict[str, Any]:
        if self.count == 0:
            return {"index": index, "name": name, "quality": 0.0, "rms": 0.0}
        rms = math.sqrt(self.total_sq / self.count)
        clipped = self.clipped / self.count
        if self.count < 2 or self.maximum - self.minimum < 1e-9:
            flat = 1.0
        else:
            flat = self.flat / (self.count - 1)
        quality = max(0.0, min(100.0, 100.0 * (1.0 - flat) * (1.0 - clipped)))
        return {
            "index": index,
            "name": name,
            "quality": round(quality, 1),
            "rms": round(rms, 2),
            "flatRatio": round(flat, 4),
            "clippedRatio": round(clipped, 4),
        }


def parse_csv(text: Any, *, clipping_uv: float = 200.0) -> dict[str, Any]:
    """解析 ``muselsl record`` CSV；只保留聚合统计，不保留原始样本。"""
    if not isinstance(text, str):
        raise AdapterError("payload 必须是 CSV 字符串")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise AdapterError("CSV 超过 16MB 上限，请拆分导入")
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    for row in reader:
        if row and any(cell.strip() for cell in row):
            header = [cell.strip() for cell in row]
            break
    if header is None or len(header) < 2:
        raise AdapterError("CSV 为空或缺少列")
    time_index = 0
    for index, name in enumerate(header):
        if name.lower() in _TIME_HEADERS:
            time_index = index
            break
    channel_indexes = [index for index in range(len(header)) if index != time_index]
    names = [header[index] or f"ch{index + 1}" for index in channel_indexes]
    stats = [_ChannelStats() for _ in names]
    times: list[float] = []
    rows = 0
    last_index = max(channel_indexes)
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) <= last_index:
            raise AdapterError(f"第 {rows + 2} 行列数不足")
        times.append(_parse_time(row[time_index], rows + 2))
        for slot, index in enumerate(channel_indexes):
            try:
                value = float(row[index])
            except ValueError as exc:
                raise AdapterError(f"第 {rows + 2} 行 {header[index]} 不是数字") from exc
            stats[slot].add(value, clipping_uv)
        rows += 1
        if rows > MAX_ROWS:
            raise AdapterError(f"CSV 超过 {MAX_ROWS} 行上限")
    if rows == 0:
        raise AdapterError("CSV 没有数据行")
    deltas = sorted(b - a for a, b in pairwise(times) if b > a)
    sample_rate = round(1.0 / deltas[len(deltas) // 2], 3) if deltas else 256.0
    duration = (max(times) - min(times)) if len(times) >= 2 else rows / sample_rate
    if duration <= 0:
        duration = rows / sample_rate
    channels = [stat.summary(name, index) for index, (stat, name) in enumerate(zip(stats, names,
                                                                                    strict=False))]
    overall = round(sum(item["quality"] for item in channels) / len(channels), 1)
    return {
        "channelNames": names,
        "sampleCount": rows,
        "sampleRate": sample_rate,
        "durationSeconds": round(duration, 3),
        "quality": {"channels": channels, "overall": overall, "ok": overall >= 60.0},
        "note": DISCLAIMER,
    }


def summarize_recording(
    parsed: Any, preset: str = "muse-2", captured_at: str | None = None
) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise AdapterError("parsed 必须是 parse_csv 的结果")
    names = parsed.get("channelNames")
    if not isinstance(names, list) or not names:
        raise AdapterError("parsed.channelNames 缺失")
    rate = parsed.get("sampleRate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        raise AdapterError("parsed.sampleRate 非法")
    duration = parsed.get("durationSeconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise AdapterError("parsed.durationSeconds 非法")
    quality = parsed.get("quality") if isinstance(parsed.get("quality"), dict) else {}
    score = quality.get("overall", 0.0)
    payload = {
        "capturedAt": captured_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preset": str(preset)[:32],
        "sampleRate": float(rate),
        "channelCount": len(names),
        "durationSeconds": round(float(duration), 3),
        "durationMinutes": round(float(duration) / 60.0, 2),
        "quality": round(max(0.0, min(100.0, float(score))), 1),
        "source": SOURCE,
    }
    return {"recordType": "eeg.session", "payload": payload, "note": DISCLAIMER}


def records_from_csv(
    text: Any, preset: str = "muse-2", captured_at: str | None = None
) -> dict[str, Any]:
    parsed = parse_csv(text)
    record = summarize_recording(parsed, preset, captured_at)
    return {"records": [record], "parsed": parsed, "note": DISCLAIMER}


def build_stream_command(preset: Any, address: Any = None) -> list[str]:
    names = channel_names(preset)
    command = ["muselsl", "stream", "--preset", str(preset)]
    if address is not None:
        if not isinstance(address, str) or not re.fullmatch(r"[A-Za-z0-9:_\-.]{1,64}", address):
            raise AdapterError("address 必须是 1..64 位设备地址/MAC")
        command.extend(["--address", address])
    del names  # 只用于校验 preset
    return command


def summarize_records(records: Any) -> dict[str, Any]:
    if not isinstance(records, list):
        raise AdapterError("records 必须是数组")
    latest: dict[str, Any] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        if item.get("recordType") not in (None, "eeg.session"):
            continue
        minutes = payload.get("durationMinutes")
        if isinstance(minutes, (int, float)) and not isinstance(minutes, bool):
            latest = {
                "durationMinutes": float(minutes),
                "at": payload.get("capturedAt"),
                "quality": payload.get("quality"),
            }
    return {"latest": latest, "note": DISCLAIMER}


def channels_for(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("quality"), dict):
        raise AdapterError("parsed.quality 缺失")
    channels = parsed["quality"].get("channels")
    if not isinstance(channels, list):
        raise AdapterError("parsed.quality.channels 缺失")
    return {"items": channels, "count": len(channels), "note": DISCLAIMER}

"""BrainFlow 适配层：板卡映射、信号质量、JSONL 导入（纯标准库）。

上游 ``brainflow`` 与 ``numpy`` 只在 ``main.py`` 连接/采样时懒加载。
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "brainflow"
MAX_CHANNELS = 64
MAX_RECORDS = 500
MAX_TEXT_BYTES = 8_000_000

BOARDS: dict[str, int] = {
    "synthetic": -1,
    "cyton": 0,
    "cyton-daisy": 1,
    "ganglion": 4,
    "cyton-wifi": 5,
    "ganglion-native": 6,
    "muse-2": 21,
    "muse-s": 22,
}


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_board(value: Any) -> tuple[str, int]:
    """接受别名或整数 BoardShim ID。"""
    if isinstance(value, str) and value.strip():
        name = value.strip().lower()
        if name in BOARDS:
            return name, BOARDS[name]
        raise AdapterError(f"未知 BrainFlow 板卡别名：{name[:32]}")
    if isinstance(value, int) and not isinstance(value, bool):
        for name, board_id in BOARDS.items():
            if board_id == value:
                return name, board_id
        raise AdapterError(f"不支持的 BoardShim ID：{value}")
    raise AdapterError("board 必须是别名或整数 ID")


def boards_payload() -> dict[str, Any]:
    return {
        "items": [{"name": name, "id": board_id} for name, board_id in BOARDS.items()],
        "note": DISCLAIMER,
    }


def channel_names(count: int, names: Any = None) -> list[str]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_CHANNELS:
        raise AdapterError(f"channelCount 必须是 1..{MAX_CHANNELS} 的整数")
    if names is None:
        return [f"ch{index + 1}" for index in range(count)]
    if not isinstance(names, list) or len(names) != count:
        raise AdapterError("channels 名称数量必须与 channelCount 一致")
    result = []
    for index, name in enumerate(names):
        if not isinstance(name, str) or not name.strip():
            raise AdapterError(f"通道 {index} 名称缺失")
        result.append(name.strip()[:32])
    return result


def _channel_quality(samples: Any, clipping_uv: float) -> dict[str, float]:
    if not isinstance(samples, list):
        raise AdapterError("通道 samples 必须是数组")
    values: list[float] = []
    for item in samples:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise AdapterError("samples 只能包含数字")
        values.append(float(item))
    if not values:
        return {"quality": 0.0, "rms": 0.0, "flatRatio": 1.0, "clippedRatio": 0.0}
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    clipped = sum(1 for value in values if abs(value) >= clipping_uv) / len(values)
    if len(values) < 2 or max(values) - min(values) < 1e-9:
        flat = 1.0
    else:
        flat = sum(
            1 for left, right in pairwise(values) if abs(left - right) < 1e-9
        ) / (len(values) - 1)
    quality = max(0.0, min(100.0, 100.0 * (1.0 - flat) * (1.0 - clipped)))
    return {
        "quality": round(quality, 1),
        "rms": round(rms, 2),
        "flatRatio": round(flat, 4),
        "clippedRatio": round(clipped, 4),
    }


def compute_signal_quality(
    channels: Any, *, names: Any = None, clipping_uv: float = 200.0
) -> dict[str, Any]:
    """按通道列表计算质量；``channels`` 是 ``[[sample, ...], ...]``。"""
    if not isinstance(channels, list) or not channels:
        raise AdapterError("channels 必须是非空数组")
    if len(channels) > MAX_CHANNELS:
        raise AdapterError(f"通道数不能超过 {MAX_CHANNELS}")
    if clipping_uv <= 0:
        raise AdapterError("clippingUv 必须为正数")
    labels = channel_names(len(channels), names)
    items = []
    for index, samples in enumerate(channels):
        stats = _channel_quality(samples, clipping_uv)
        items.append({"index": index, "name": labels[index], **stats})
    overall = round(sum(item["quality"] for item in items) / len(items), 1)
    return {"channels": items, "overall": overall, "ok": overall >= 60.0, "note": DISCLAIMER}


def summarize_session(
    *,
    board: str,
    sample_rate: Any,
    channel_count: int,
    duration_seconds: Any,
    quality: Any,
    captured_at: str | None = None,
) -> dict[str, Any]:
    rate = _positive(sample_rate, "sampleRate")
    duration = _positive(duration_seconds, "durationSeconds", allow_zero=True)
    score = quality if isinstance(quality, (int, float)) and not isinstance(quality, bool) else 0.0
    payload = {
        "capturedAt": captured_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "board": board,
        "sampleRate": rate,
        "channelCount": int(channel_count),
        "durationSeconds": round(duration, 3),
        "quality": round(max(0.0, min(100.0, float(score))), 1),
        "source": SOURCE,
    }
    return {"recordType": "eeg.session", "payload": payload, "note": DISCLAIMER}


def _positive(value: Any, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{field} 必须是数字")
    minimum = 0 if allow_zero else 1e-9
    if value < minimum:
        raise AdapterError(f"{field} 必须为正数")
    return float(value)


def parse_jsonl(text: Any) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        raise AdapterError("payload 必须是 JSONL 字符串")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise AdapterError("JSONL 超过 8MB 上限，请拆分导入")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"第 {number} 行不是合法 JSON") from exc
        if not isinstance(item, dict):
            raise AdapterError(f"第 {number} 行必须是 JSON 对象")
        records.append(item)
        if len(records) > MAX_RECORDS:
            raise AdapterError(f"单次最多导入 {MAX_RECORDS} 条记录")
    return records


def records_from_jsonl(text: Any) -> list[dict[str, Any]]:
    records = []
    for item in parse_jsonl(text):
        board = item.get("board")
        if not isinstance(board, str) or not board.strip():
            raise AdapterError("记录缺少 board")
        channels = item.get("channels")
        if not isinstance(channels, list) or not channels:
            raise AdapterError("记录缺少 channels")
        samples = [channel.get("samples") for channel in channels if isinstance(channel, dict)]
        if len(samples) != len(channels):
            raise AdapterError("channels 条目必须是对象")
        names = [str(channel.get("name") or f"ch{index + 1}") for index, channel in enumerate(channels)]
        quality = compute_signal_quality(samples, names=names)
        rate = _positive(item.get("sampleRate"), "sampleRate")
        longest = max((len(part) for part in samples if isinstance(part, list)), default=0)
        records.append(
            summarize_session(
                board=board.strip(),
                sample_rate=rate,
                channel_count=len(channels),
                duration_seconds=longest / rate,
                quality=quality["overall"],
                captured_at=item.get("capturedAt") if isinstance(item.get("capturedAt"), str) else None,
            )
        )
    return records


def summarize_quality(quality: Any) -> dict[str, Any]:
    if not isinstance(quality, dict) or not isinstance(quality.get("channels"), list):
        raise AdapterError("quality 必须是 compute_signal_quality 的结果")
    overall = quality.get("overall", 0.0)
    return {
        "latest": {"quality": overall, "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "channels": quality["channels"],
        "ok": bool(quality.get("ok")),
        "note": DISCLAIMER,
    }


def channels_for(quality: Any) -> dict[str, Any]:
    if not isinstance(quality, dict) or not isinstance(quality.get("channels"), list):
        raise AdapterError("quality 必须是 compute_signal_quality 的结果")
    items = quality["channels"][:MAX_CHANNELS]
    return {"items": items, "count": len(items), "note": DISCLAIMER}

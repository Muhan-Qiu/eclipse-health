"""OpenBCI_Python 适配层：串口名校验、raw text 解析、质量摘要（纯标准库）。

上游 ``openbci``/pyserial 只在 ``main.py`` 启动流时懒加载。
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

DISCLAIMER = "非医疗器械，不用于诊断"
SOURCE = "openbci"
MAX_TEXT_BYTES = 32_000_000
MAX_ROWS = 1_000_000

BOARDS: dict[str, int] = {"cyton": 8, "cyton-daisy": 16, "ganglion": 4}
_PORT_RE = re.compile(r"^(?:COM[0-9]{1,3}|/dev/tty[A-Za-z0-9._-]{1,64})$")


class AdapterError(Exception):
    """可映射为 JSON-RPC ``INVALID_INPUT`` 的适配错误。"""

    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_board(value: Any) -> tuple[str, int]:
    if not isinstance(value, str) or value not in BOARDS:
        raise AdapterError(f"board 必须是 {', '.join(sorted(BOARDS))}")
    return value, BOARDS[value]


def resolve_port(value: Any) -> str:
    if not isinstance(value, str) or not _PORT_RE.fullmatch(value.strip()):
        raise AdapterError("port 必须是 COMx 或 /dev/tty* 串口名")
    return value.strip()


def devices_payload() -> dict[str, Any]:
    return {
        "items": [{"board": name, "channelCount": count} for name, count in BOARDS.items()],
        "note": DISCLAIMER,
    }


class _ChannelStats:
    __slots__ = ("clipped", "count", "flat", "maximum", "minimum", "previous", "total_sq")

    def __init__(self) -> None:
        self.count = 0
        self.total_sq = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.previous: float | None = None
        self.flat = 0
        self.clipped = 0

    def add(self, value: float, clipping_uv: float) -> None:
        self.count += 1
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


def parse_openbci_text(
    text: Any,
    *,
    board: str = "cyton",
    sample_rate: Any = 250.0,
    clipping_uv: float = 200.0,
) -> dict[str, Any]:
    """解析 OpenBCI raw text；只保留聚合统计，不保留原始样本。"""
    if not isinstance(text, str):
        raise AdapterError("payload 必须是文本")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise AdapterError("文本超过 32MB 上限，请拆分导入")
    _, expected = resolve_board(board)
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, (int, float))
        or not 1 <= sample_rate <= 100000
    ):
        raise AdapterError("sampleRate 必须在 1..100000")
    stats = [_ChannelStats() for _ in range(expected)]
    rows = 0
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("%", "#")):
            continue
        cells = [cell.strip() for cell in stripped.split(",")]
        if len(cells) < expected + 1:
            raise AdapterError(f"第 {number} 行列数不足（需要 {expected + 1} 列）")
        try:
            int(cells[0])
        except ValueError as exc:
            raise AdapterError(f"第 {number} 行样本序号不是整数") from exc
        for index in range(expected):
            try:
                value = float(cells[index + 1])
            except ValueError as exc:
                raise AdapterError(f"第 {number} 行通道 {index + 1} 不是数字") from exc
            stats[index].add(value, clipping_uv)
        rows += 1
        if rows > MAX_ROWS:
            raise AdapterError(f"文本超过 {MAX_ROWS} 行上限")
    if rows == 0:
        raise AdapterError("文本没有数据行")
    channels = [
        stat.summary(f"ch{index + 1}", index) for index, stat in enumerate(stats)
    ]
    overall = round(sum(item["quality"] for item in channels) / len(channels), 1)
    return {
        "channelNames": [item["name"] for item in channels],
        "sampleCount": rows,
        "sampleRate": float(sample_rate),
        "durationSeconds": round(rows / float(sample_rate), 3),
        "quality": {"channels": channels, "overall": overall, "ok": overall >= 60.0},
        "note": DISCLAIMER,
    }


def summarize_recording(
    parsed: Any, board: str = "cyton", captured_at: str | None = None
) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise AdapterError("parsed 必须是 parse_openbci_text 的结果")
    names = parsed.get("channelNames")
    rate = parsed.get("sampleRate")
    if not isinstance(names, list) or not names:
        raise AdapterError("parsed.channelNames 缺失")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        raise AdapterError("parsed.sampleRate 非法")
    quality = parsed.get("quality") if isinstance(parsed.get("quality"), dict) else {}
    score = quality.get("overall", 0.0)
    payload = {
        "capturedAt": captured_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "board": board,
        "sampleRate": float(rate),
        "channelCount": len(names),
        "durationSeconds": round(float(parsed.get("durationSeconds") or 0.0), 3),
        "quality": round(max(0.0, min(100.0, float(score))), 1),
        "source": SOURCE,
    }
    return {"recordType": "eeg.session", "payload": payload, "note": DISCLAIMER}


def records_from_text(
    text: Any,
    *,
    board: str = "cyton",
    sample_rate: Any = 250.0,
    captured_at: str | None = None,
) -> dict[str, Any]:
    parsed = parse_openbci_text(text, board=board, sample_rate=sample_rate)
    record = summarize_recording(parsed, board, captured_at)
    return {"records": [record], "parsed": parsed, "note": DISCLAIMER}


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
        count = payload.get("channelCount")
        if isinstance(count, int) and not isinstance(count, bool):
            latest = {
                "channelCount": count,
                "quality": payload.get("quality"),
                "at": payload.get("capturedAt"),
            }
    return {"latest": latest, "note": DISCLAIMER}


def channels_for(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("quality"), dict):
        raise AdapterError("parsed.quality 缺失")
    channels = parsed["quality"].get("channels")
    if not isinstance(channels, list):
        raise AdapterError("parsed.quality.channels 缺失")
    return {"items": channels, "count": len(channels), "note": DISCLAIMER}

"""合成小米运动 ``hlth_center_fitness_data.csv``（Key,Time,Value）。"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

START = datetime(2026, 10, 28, 2, 0, tzinfo=UTC)


def epoch(minutes: int = 0) -> int:
    return int(START.timestamp()) + minutes * 60


def row(key: str, value: object, *, minutes: int = 0) -> list[str]:
    return [key, str(epoch(minutes)), json.dumps(value, ensure_ascii=False)]


def fitness_csv(*, extra_rows: list[list[str]] | None = None, header: str = "Key,Time,Value") -> str:
    rows: list[list[str]] = [
        header.split(","),
        row("steps", {"steps": 1000}, minutes=0),
        row("steps", {"steps": 1200}, minutes=10),
        row("heart_rate", {"heart_rate": 72}, minutes=0),
        row("heart_rate", {"heart_rate": 75}, minutes=5),
        row(
            "sleep",
            {
                "start_time": epoch(0) * 1000,
                "end_time": epoch(120) * 1000,
                "stage": "deep",
            },
            minutes=0,
        ),
        row("weight", {"weight": 70.5}, minutes=0),
    ]
    rows.extend(extra_rows or [])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


__all__ = ["START", "epoch", "fitness_csv", "row"]

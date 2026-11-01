"""YASA 适配层的纯函数：睡眠分期序列校验、睡眠效率、分期统计。

不 import yasa，保证单元测试无需 mne/lightgbm。
"""

from __future__ import annotations

import math
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
SLEEP_STAGES = frozenset({"N1", "N2", "N3", "R"})
KNOWN_STAGES = frozenset({"W", "N1", "N2", "N3", "R", "ART", "UNS", "UNKNOWN"})
MAX_EPOCHS = 200_000


class AdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_stage(value: Any) -> str:
    if not isinstance(value, str):
        raise AdapterError("invalid_input", "stage 必须是字符串")
    stage = value.strip().upper().replace("REM", "R")
    if stage not in KNOWN_STAGES:
        raise AdapterError("invalid_input", f"未知睡眠分期 {value[:16]}")
    return stage


def parse_stages(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise AdapterError("invalid_input", "stages 必须是分期字符串数组")
    if not values:
        raise AdapterError("invalid_input", "stages 不能为空")
    if len(values) > MAX_EPOCHS:
        raise AdapterError("invalid_input", f"stages 超过 {MAX_EPOCHS} 个 epoch 上限")
    return [normalize_stage(item) for item in values]


def sleep_efficiency(values: Any, epoch_seconds: float = 30.0) -> dict[str, Any]:
    stages = parse_stages(values)
    if not isinstance(epoch_seconds, (int, float)) or isinstance(epoch_seconds, bool):
        raise AdapterError("invalid_input", "epochSeconds 必须是数值")
    epoch = float(epoch_seconds)
    if not math.isfinite(epoch) or not 0.1 <= epoch <= 300:
        raise AdapterError("invalid_input", "epochSeconds 必须在 0.1–300 秒之间")

    counts: dict[str, int] = {}
    for stage in stages:
        counts[stage] = counts.get(stage, 0) + 1
    sleep_epochs = sum(count for stage, count in counts.items() if stage in SLEEP_STAGES)
    total_minutes = round(len(stages) * epoch / 60.0, 2)
    sleep_minutes = round(sleep_epochs * epoch / 60.0, 2)
    efficiency = round(100.0 * sleep_epochs / len(stages), 2)
    return {
        "efficiency": efficiency,
        "totalMinutes": total_minutes,
        "sleepMinutes": sleep_minutes,
        "epochs": len(stages),
        "epochSeconds": epoch,
        "stageCounts": counts,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def stage_rows(counts: dict[str, int], epoch_seconds: float = 30.0) -> list[dict[str, Any]]:
    return [
        {"stage": stage, "epochs": count, "minutes": round(count * epoch_seconds / 60.0, 2)}
        for stage, count in sorted(counts.items())
    ]


def widget_stats(values: Any, epoch_seconds: float = 30.0) -> dict[str, Any]:
    if values is None:
        return {
            "latest": {"efficiency": 0.0},
            "series": [],
            "stageRows": [],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    result = sleep_efficiency(values, epoch_seconds)
    stages = parse_stages(values)
    return {
        "latest": {"efficiency": result["efficiency"]},
        "series": [{"value": 1 if stage in SLEEP_STAGES else 0} for stage in stages],
        "stageRows": stage_rows(result["stageCounts"], float(epoch_seconds)),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

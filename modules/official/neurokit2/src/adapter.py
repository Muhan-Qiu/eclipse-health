"""NeuroKit2 适配层的纯函数：RR 校验、时域指标、上游结果映射。

这里不 import 第三方库，保证单元测试无需安装 neurokit2。
"""

from __future__ import annotations

import math
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
RR_MIN_MS = 200.0
RR_MAX_MS = 3000.0


class AdapterError(ValueError):
    """输入不可用时抛出；main.py 会映射为 JSON-RPC INVALID_INPUT。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_rr(values: Any) -> list[float]:
    """校验 RR 间期数组（毫秒），返回浮点列表。"""
    if not isinstance(values, (list, tuple)):
        raise AdapterError("invalid_input", "rr 必须是毫秒为单位的 RR 间期数组")
    result: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AdapterError("invalid_input", f"rr[{index}] 不是数值")
        number = float(value)
        if not math.isfinite(number) or not RR_MIN_MS <= number <= RR_MAX_MS:
            raise AdapterError("invalid_input", f"rr[{index}] 超出 {RR_MIN_MS:.0f}–{RR_MAX_MS:.0f} ms")
        result.append(number)
    if len(result) < 2:
        raise AdapterError("too_few_intervals", "至少需要 2 个 RR 间期")
    return result


def time_domain(rr: list[float]) -> dict[str, float]:
    """纯 Python 时域指标，与上游库实现互相校验。"""
    n = len(rr)
    mean_rr = sum(rr) / n
    diffs = [rr[i + 1] - rr[i] for i in range(n - 1)]
    sdnn = (sum((x - mean_rr) ** 2 for x in rr) / (n - 1)) ** 0.5
    rmssd = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
    over50 = sum(1 for d in diffs if abs(d) > 50.0)
    return {
        "meanRr": round(mean_rr, 2),
        "meanHr": round(60000.0 / mean_rr, 2),
        "sdnn": round(sdnn, 2),
        "rmssd": round(rmssd, 2),
        "pnn50": round(100.0 * over50 / len(diffs), 2),
        "intervals": float(n),
    }


def map_neurokit_hrv(raw: dict[str, Any]) -> dict[str, float | None]:
    """把 nk.hrv_time 的列名映射为稳定键；缺失返回 None。"""

    def pick(*keys: str) -> float | None:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return round(float(value), 2)
        return None

    return {
        "meanRr": pick("MeanNN"),
        "sdnn": pick("SDNN"),
        "rmssd": pick("RMSSD"),
        "pnn50": pick("pNN50"),
    }


def build_summary(rr: list[float], source: str) -> dict[str, Any]:
    return {"source": source, "hrv": time_domain(rr), "nonDiagnostic": NON_DIAGNOSTIC}


def widget_stats(rr: Any) -> dict[str, Any]:
    """widget/pages 的 stats 结果；无输入时返回零值骨架。"""
    if rr is None:
        return {
            "latest": {"rmssd": 0.0, "sdnn": 0.0, "meanHr": 0.0},
            "series": [],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    parsed = parse_rr(rr)
    metrics = time_domain(parsed)
    return {
        "latest": {"rmssd": metrics["rmssd"], "sdnn": metrics["sdnn"], "meanHr": metrics["meanHr"]},
        "series": [{"value": round(value, 2)} for value in parsed],
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

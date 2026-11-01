"""pyhrv 适配层的纯函数：RR 校验、时域指标与上游结果映射。

不 import pyhrv，保证单元测试无需 biosppy/spectrum/nolds。
"""

from __future__ import annotations

import math
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
RR_MIN_MS = 200.0
RR_MAX_MS = 3000.0


class AdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_rr(values: Any) -> list[float]:
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


def _finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return round(float(value), 4)
    return None


def map_pyhrv_time(raw: dict[str, Any]) -> dict[str, float | None]:
    """pyhrv.time_domain 返回 dict 的稳定映射。"""
    return {
        "meanRr": _finite_number(raw.get("nni_mean")),
        "meanHr": _finite_number(raw.get("hr_mean")),
        "sdnn": _finite_number(raw.get("sdnn")),
        "rmssd": _finite_number(raw.get("rmssd")),
        "pnn50": _finite_number(raw.get("pnn50")),
    }


def metric_rows(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    return [{"name": name, "value": value} for name, value in metrics.items() if value is not None]


def build_summary(rr: list[float], source: str = "rr") -> dict[str, Any]:
    metrics = time_domain(rr)
    return {"source": source, "hrv": metrics, "metrics": metric_rows(metrics), "nonDiagnostic": NON_DIAGNOSTIC}


def widget_stats(rr: Any) -> dict[str, Any]:
    if rr is None:
        return {
            "latest": {"rmssd": 0.0, "sdnn": 0.0},
            "series": [],
            "metrics": [],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    parsed = parse_rr(rr)
    metrics = time_domain(parsed)
    return {
        "latest": {"rmssd": metrics["rmssd"], "sdnn": metrics["sdnn"]},
        "series": [{"value": round(value, 2)} for value in parsed],
        "metrics": metric_rows(metrics),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

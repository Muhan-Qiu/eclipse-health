"""HeartPy 适配层的纯函数：RR 校验、时域指标、质量标志与上游结果映射。

不 import heartpy，保证单元测试可在核心 venv 直接运行。
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
        "bpm": round(60000.0 / mean_rr, 2),
        "sdnn": round(sdnn, 2),
        "rmssd": round(rmssd, 2),
        "pnn50": round(100.0 * over50 / len(diffs), 2),
        "intervals": float(n),
    }


def quality_flags(accepted: Any, bpm: Any = None) -> dict[str, Any]:
    """把 HeartPy 的 binary_quality_score 转成稳定质量描述。"""
    is_ok = bool(accepted)
    bpm_value = float(bpm) if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) else None
    return {
        "accepted": is_ok,
        "label": "good" if is_ok else "poor",
        "bpm": round(bpm_value, 2) if bpm_value is not None else None,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def quality_from_rr(values: Any) -> dict[str, Any]:
    """无原始波形时的保守质量判断：数量与间期范围。"""
    try:
        rr = parse_rr(values)
    except AdapterError as error:
        return {"accepted": False, "label": "invalid", "reason": error.message, "nonDiagnostic": NON_DIAGNOSTIC}
    accepted = 10 <= len(rr) <= 5000
    reason = None if accepted else "RR 间期数量不足 10 个，质量置信度低"
    return {
        "accepted": accepted,
        "label": "good" if accepted else "poor",
        "reason": reason,
        "intervals": len(rr),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def map_heartpy_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    """映射 hp.process 返回的 measures 字典。"""

    def number(key: str) -> float | None:
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(float(value), 2)
        return None

    return {
        "bpm": number("bpm"),
        "rmssd": number("rmssd"),
        "sdnn": number("sdnn"),
        "pnn50": number("pnn50"),
    }


def build_summary(rr: list[float], source: str) -> dict[str, Any]:
    return {"source": source, "hrv": time_domain(rr), "quality": quality_from_rr(rr), "nonDiagnostic": NON_DIAGNOSTIC}


def widget_stats(rr: Any) -> dict[str, Any]:
    if rr is None:
        return {
            "latest": {"rmssd": 0.0, "sdnn": 0.0, "bpm": 0.0},
            "series": [],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    parsed = parse_rr(rr)
    metrics = time_domain(parsed)
    return {
        "latest": {"rmssd": metrics["rmssd"], "sdnn": metrics["sdnn"], "bpm": metrics["bpm"]},
        "series": [
            {"rmssd": metrics["rmssd"], "sdnn": metrics["sdnn"]},
        ],
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

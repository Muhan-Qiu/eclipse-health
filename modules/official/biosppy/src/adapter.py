"""BioSPPy 适配层的纯函数：RR 校验、R 峰→RR、时域指标与质量判断。

不 import biosppy，保证单元测试无需 h5py/scikit-learn。
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


def rpeaks_to_rr(rpeaks: Any, fs: float) -> list[float]:
    """把样本索引 R 峰转换为毫秒 RR 间期。"""
    if not isinstance(fs, (int, float)) or isinstance(fs, bool) or not math.isfinite(float(fs)) or fs <= 0:
        raise AdapterError("invalid_input", "fs 必须是正数")
    if not isinstance(rpeaks, (list, tuple)):
        raise AdapterError("invalid_input", "rpeaks 必须是数组")
    peaks: list[float] = []
    for index, peak in enumerate(rpeaks):
        if isinstance(peak, bool) or not isinstance(peak, (int, float)):
            raise AdapterError("invalid_input", f"rpeaks[{index}] 不是数值")
        peaks.append(float(peak))
    if len(peaks) < 3:
        raise AdapterError("too_few_intervals", "R 峰少于 3 个，无法计算 RR 间期")
    rr = [(peaks[i + 1] - peaks[i]) * 1000.0 / float(fs) for i in range(len(peaks) - 1)]
    return parse_rr(rr)


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


def quality_from_rr(values: Any) -> dict[str, Any]:
    try:
        rr = parse_rr(values)
    except AdapterError as error:
        return {"accepted": False, "label": "invalid", "reason": error.message, "nonDiagnostic": NON_DIAGNOSTIC}
    accepted = 10 <= len(rr) <= 5000
    return {
        "accepted": accepted,
        "label": "good" if accepted else "poor",
        "reason": None if accepted else "RR 数量不足 10，质量置信度低",
        "intervals": len(rr),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def build_summary(rr: list[float], n_peaks: int | None = None, source: str = "rr") -> dict[str, Any]:
    metrics = time_domain(rr)
    return {
        "source": source,
        "nPeaks": int(n_peaks) if n_peaks is not None else len(rr) + 1,
        "hrv": metrics,
        "quality": quality_from_rr(rr),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def widget_stats(rr: Any) -> dict[str, Any]:
    if rr is None:
        return {
            "latest": {"meanHr": 0.0, "rmssd": 0.0},
            "series": [],
            "segments": [],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    parsed = parse_rr(rr)
    metrics = time_domain(parsed)
    return {
        "latest": {"meanHr": metrics["meanHr"], "rmssd": metrics["rmssd"]},
        "series": [{"value": round(value, 2)} for value in parsed],
        "segments": [{"meanHr": metrics["meanHr"], "rmssd": metrics["rmssd"]}],
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

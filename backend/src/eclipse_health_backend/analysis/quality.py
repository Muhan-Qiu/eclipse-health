"""信号质量评估。

只做工程意义上的可用性判断（幅度、平线、削顶、高频噪声、RR 异常），
不是临床质量分级；输出结构见 ``docs/DATA_SCHEMA_V1.md`` §8.3。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import welch

from .types import EcgSignal

FLAT_EPS_MV = 1e-6
MIN_FLAT_SEC = 0.2
CLIP_FRACTION_WARN = 0.005
HF_RATIO_WARN = 0.10
RR_DEVIATION = 0.20
RR_FRACTION_WARN = 0.40


@dataclass
class QualityResult:
    score: float
    level: str
    warnings: list[dict[str, Any]] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "warnings": list(self.warnings),
            "segments": list(self.segments),
        }


def _warning(
    code: str,
    message: str,
    severity: str = "warning",
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "startSec": start_sec,
        "endSec": end_sec,
    }


def _longest_flat_run(x: np.ndarray, fs: float) -> tuple[int, float, float]:
    """返回最长近平线区段的 (样本数, 起点秒, 终点秒)。"""
    flat = np.abs(np.diff(x)) < FLAT_EPS_MV
    if not flat.any():
        return 0, 0.0, 0.0
    padded = np.concatenate(([False], flat, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    min_len = max(2, round(MIN_FLAT_SEC * fs))
    best = (0, 0, 0)
    for start, end in zip(starts, ends):
        length = int(end - start)
        if length >= min_len and length > best[0]:
            best = (length, int(start), int(end))
    return best[0], best[1] / fs, best[2] / fs


def _clipping_fraction(x: np.ndarray) -> float:
    lo = float(np.min(x))
    hi = float(np.max(x))
    if hi - lo <= 0:
        return 1.0
    at_lo = x <= lo + 1e-9
    at_hi = x >= hi - 1e-9
    return float(np.mean(at_lo | at_hi))


def _hf_noise_ratio(x: np.ndarray, fs: float) -> float:
    if len(x) < 16 or fs <= 80:
        return 0.0
    nperseg = min(2048, len(x))
    freqs, psd = welch(x, fs=fs, nperseg=nperseg)
    total = float(psd.sum())
    if total <= 0:
        return 0.0
    return float(psd[freqs >= 40].sum() / total)


def _rr_abnormal_fraction(rpeaks: np.ndarray, fs: float) -> tuple[float, float]:
    rr = np.diff(np.asarray(rpeaks, dtype=np.float64)) / fs
    if len(rr) < 5:
        return 0.0, 0.0
    local = median_filter(rr, size=min(11, len(rr)))
    deviation = np.abs(rr - local) / np.maximum(local, 1e-9)
    fraction = float(np.mean(deviation > RR_DEVIATION))
    cv = float(np.std(rr, ddof=1) / np.mean(rr)) if np.mean(rr) > 0 else 0.0
    return fraction, cv


def assess_quality(signal: EcgSignal, rpeaks: np.ndarray) -> QualityResult:
    x = np.asarray(signal.samples, dtype=np.float64)
    fs = signal.fs
    n = len(x)

    amplitude_mv = float(np.percentile(x, 99.5) - np.percentile(x, 0.5))
    flat_samples, flat_start, flat_end = _longest_flat_run(x, fs)
    flat_fraction = flat_samples / n
    clip_fraction = _clipping_fraction(x)
    hf_ratio = _hf_noise_ratio(x, fs)
    rr_fraction, rr_cv = _rr_abnormal_fraction(rpeaks, fs)

    if amplitude_mv < 0.05:
        amp_penalty = 1.0
    elif amplitude_mv < 0.2:
        amp_penalty = 0.5
    elif amplitude_mv > 10.0:
        amp_penalty = 1.0
    elif amplitude_mv > 5.0:
        amp_penalty = 0.5
    else:
        amp_penalty = 0.0

    flat_penalty = min(1.0, flat_fraction / 0.10)
    clip_penalty = (
        0.0
        if clip_fraction < CLIP_FRACTION_WARN
        else min(1.0, (clip_fraction - CLIP_FRACTION_WARN) / 0.02)
    )
    hf_penalty = min(1.0, max(0.0, (hf_ratio - HF_RATIO_WARN) / 0.30))
    # RR 不齐多由真实心律失常引起，不能当成“信号差”重罚；只在极端时提示。
    rr_penalty = (
        0.0
        if rr_fraction < RR_FRACTION_WARN
        else min(1.0, (rr_fraction - RR_FRACTION_WARN) / 0.40)
    )

    score = 1.0 - (
        0.25 * flat_penalty
        + 0.25 * clip_penalty
        + 0.20 * hf_penalty
        + 0.15 * amp_penalty
        + 0.15 * rr_penalty
    )
    score = round(float(min(1.0, max(0.0, score))), 3)
    level = "good" if score >= 0.80 else "fair" if score >= 0.55 else "poor"

    warnings: list[dict[str, Any]] = []
    if flat_penalty > 0:
        warnings.append(
            _warning(
                "flatline",
                f"检测到约 {flat_samples / fs:.1f}s 近平线，疑似导联脱落",
                start_sec=round(flat_start, 3),
                end_sec=round(flat_end, 3),
            )
        )
    if clip_penalty > 0:
        warnings.append(
            _warning(
                "clipping",
                f"{clip_fraction:.2%} 的采样点贴住极值，疑似削顶或饱和",
            )
        )
    if hf_penalty > 0:
        warnings.append(
            _warning(
                "high_frequency_noise",
                f"40 Hz 以上能量占比 {hf_ratio:.1%}，高频噪声偏高",
            )
        )
    if amp_penalty > 0:
        warnings.append(
            _warning(
                "low_amplitude" if amplitude_mv < 0.2 else "amplitude_out_of_range",
                f"峰峰幅度约 {amplitude_mv:.2f} mV，超出常见单导联范围",
            )
        )
    if rr_penalty > 0:
        warnings.append(
            _warning(
                "irregular_rr",
                f"{rr_fraction:.1%} 的 RR 间期偏离局部中位数超过 "
                f"{RR_DEVIATION:.0%}",
            )
        )

    metrics = {
        "amplitudeMv": round(amplitude_mv, 4),
        "flatlineFraction": round(flat_fraction, 6),
        "flatlineLongestSec": round(flat_samples / fs, 3),
        "clippingFraction": round(clip_fraction, 6),
        "hfNoiseRatio": round(hf_ratio, 4),
        "rrAbnormalFraction": round(rr_fraction, 4),
        "rrCv": round(rr_cv, 4),
        "nRpeaks": len(rpeaks),
    }
    segments = [
        {
            "startSec": 0.0,
            "endSec": round(signal.duration_sec, 3),
            "quality": score,
        }
    ]
    return QualityResult(score, level, warnings, segments, metrics)

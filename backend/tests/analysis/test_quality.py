"""信号质量：正常、平线、削顶、RR 异常。"""

from __future__ import annotations

import numpy as np

from eclipse_health_backend.analysis import load_array
from eclipse_health_backend.analysis.quality import assess_quality


def test_clean_signal_is_good(synthetic_ecg) -> None:
    signal, beat_times = synthetic_ecg(fs=360, duration=80, noise=0.005)
    sig = load_array(signal, fs=360)
    quality = assess_quality(sig, np.round(beat_times * 360).astype(int))
    assert quality.level == "good"
    assert quality.score > 0.9
    codes = {warning["code"] for warning in quality.warnings}
    assert "flatline" not in codes
    assert "clipping" not in codes


def test_flatline_detected(synthetic_ecg) -> None:
    signal, beat_times = synthetic_ecg(fs=360, duration=80)
    damaged = signal.copy()
    start = 20 * 360
    damaged[start : start + (2 * 360)] = 0.0
    sig = load_array(damaged, fs=360)
    quality = assess_quality(sig, np.round(beat_times * 360).astype(int))
    codes = {warning["code"] for warning in quality.warnings}
    assert "flatline" in codes
    assert quality.score < 1.0


def test_clipping_detected() -> None:
    fs = 360
    t = np.arange(fs * 30) / fs
    signal = np.clip(2.0 * np.sin(2 * np.pi * 1.2 * t), -0.5, 0.5)
    sig = load_array(signal, fs=fs)
    rpeaks = np.arange(200, len(signal), int(fs * 0.8))
    quality = assess_quality(sig, rpeaks)
    codes = {warning["code"] for warning in quality.warnings}
    assert "clipping" in codes


def test_irregular_rr_detected(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=80)
    sig = load_array(signal, fs=360)
    rpeaks = [100]
    for index in range(40):
        rpeaks.append(rpeaks[-1] + (180 if index % 2 == 0 else 540))
    quality = assess_quality(sig, np.asarray(rpeaks))
    codes = {warning["code"] for warning in quality.warnings}
    assert "irregular_rr" in codes


def test_segments_cover_record(synthetic_ecg) -> None:
    signal, beat_times = synthetic_ecg(fs=360, duration=20)
    sig = load_array(signal, fs=360)
    quality = assess_quality(sig, np.round(beat_times * 360).astype(int))
    assert len(quality.segments) == 1
    assert quality.segments[0]["startSec"] == 0.0
    assert abs(quality.segments[0]["endSec"] - sig.duration_sec) < 0.01

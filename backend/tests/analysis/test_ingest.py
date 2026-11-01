"""输入适配：WFDB / CSV / NPY / ndarray 与非法输入。"""

from __future__ import annotations

import numpy as np
import pytest
import wfdb

from eclipse_health_backend.analysis import (
    load_array,
    load_csv,
    load_npy,
    load_wfdb,
    resample_signal,
)
from eclipse_health_backend.analysis.types import EcgSignal, InvalidSignalError


def test_load_wfdb_mlII(samples_dir) -> None:
    sig = load_wfdb(samples_dir / "100")
    assert sig.lead == "MLII"
    assert sig.fs == 360.0
    assert sig.original_fs == 360.0
    assert sig.resampled is False
    assert sig.n_samples == 650000
    assert sig.source == "wfdb"
    assert sig.samples.dtype == np.float32
    assert np.isfinite(sig.samples).all()
    assert len(sig.annotations or []) == 2274
    assert 0.5 < float(np.percentile(np.abs(sig.samples), 99.5)) < 3.0


def test_wfdb_digital_matches_reference(samples_dir) -> None:
    sig = load_wfdb(samples_dir / "100")
    record = wfdb.rdrecord(str(samples_dir / "100"), physical=False)
    expected = record.d_signal[:, 0].astype(np.float64)
    assert sig.digital is not None
    assert np.array_equal(sig.digital, expected)


def test_wfdb_lead_selection(samples_dir) -> None:
    v5 = load_wfdb(samples_dir / "100", lead="V5")
    assert v5.lead == "V5"

    fallback = load_wfdb(samples_dir / "100", lead="X9")
    assert fallback.lead == "MLII"
    assert any(w["code"] == "lead_not_found" for w in fallback.warnings)


def test_csv_time_column_and_resample(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=500, duration=40)
    path = tmp_path / "watch.csv"
    lines = ["time,ecg"] + [
        f"{idx / 500:.6f},{value:.6f}" for idx, value in enumerate(signal)
    ]
    path.write_text("\n".join(lines), encoding="utf-8")

    sig = load_csv(path, fs=500, lead="I")
    assert sig.resampled is True
    assert sig.fs == 360.0
    assert sig.original_fs == 500.0
    assert abs(sig.duration_sec - 40.0) < 0.01
    assert abs(sig.n_samples - 40 * 360) <= 1
    assert any(w["code"] == "resampled" for w in sig.warnings)


def test_csv_explicit_column(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=10)
    path = tmp_path / "two_columns.csv"
    lines = ["a,b"] + [
        f"{0.0:.6f},{value:.6f}" for value in signal
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    sig = load_csv(path, fs=360, column=1)
    assert sig.n_samples == len(signal)


def test_npy_roundtrip(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=10)
    path = tmp_path / "signal.npy"
    np.save(path, signal)
    sig = load_npy(path, fs=360, lead="II")
    assert sig.lead == "II"
    assert sig.n_samples == len(signal)
    assert np.allclose(sig.samples, signal.astype(np.float32))


def test_unit_uv_to_mv(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=5)
    sig = load_array(signal * 1000.0, fs=360, unit="uV")
    assert np.allclose(sig.samples, signal.astype(np.float32), atol=1e-6)


def test_adc_unit_keeps_digital(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=5)
    adc = np.round(signal * 200.0)
    sig = load_array(adc, fs=360, unit="ADC")
    assert sig.digital is not None
    assert np.array_equal(sig.digital, adc)
    assert np.allclose(sig.samples, (adc - np.median(adc)) / 200.0, atol=1e-5)


def test_empty_array_rejected() -> None:
    with pytest.raises(InvalidSignalError):
        load_array([], fs=360)


def test_non_positive_fs_rejected(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=5)
    for bad_fs in (0, -1):
        with pytest.raises(InvalidSignalError):
            load_array(signal, fs=bad_fs)


def test_nan_rejected() -> None:
    with pytest.raises(InvalidSignalError):
        load_array([1.0, np.nan, 3.0], fs=360)


def test_constant_rejected() -> None:
    with pytest.raises(InvalidSignalError):
        load_array([1.0] * 100, fs=360)


def test_csv_without_numbers_rejected(tmp_path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("time,ecg\n", encoding="utf-8")
    with pytest.raises(InvalidSignalError):
        load_csv(path, fs=500)


def test_column_out_of_range(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=360, duration=5)
    path = tmp_path / "single.csv"
    path.write_text("\n".join(f"{v:.6f}" for v in signal), encoding="utf-8")
    with pytest.raises(InvalidSignalError):
        load_csv(path, fs=360, column=3)


def test_resampled_annotations_scale(synthetic_ecg) -> None:
    signal, beat_times = synthetic_ecg(fs=500, duration=10)
    annotations = [(round(t * 500), "N") for t in beat_times]
    raw = EcgSignal(samples=signal, fs=500, lead="I", annotations=annotations)
    sig = resample_signal(raw)
    assert sig.annotations is not None
    assert len(sig.annotations) == len(annotations)
    first = sig.annotations[0][0]
    assert abs(first - round(annotations[0][0] * 360 / 500)) <= 1

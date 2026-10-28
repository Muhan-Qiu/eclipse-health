"""短记录与非 360 Hz 输入。"""

from __future__ import annotations

import pytest

from eclipse_health_backend.analysis import (
    AnalysisOptions,
    InsufficientBeatsError,
    analyze,
    load_array,
)


def test_short_record_raises_by_default(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=500, duration=18, heart_rate=72)
    sig = load_array(signal, fs=500, lead="I")
    with pytest.raises(InsufficientBeatsError, match="allow_short_record"):
        analyze(sig, AnalysisOptions(record_id="rec_short"))


def test_short_record_can_be_padded(synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=500, duration=18, heart_rate=72)
    sig = load_array(signal, fs=500, lead="I")
    result = analyze(
        sig,
        AnalysisOptions(record_id="rec_short", allow_short_record=True),
    )
    assert result["parameters"]["nBeatsClassified"] < 64
    assert result["parameters"]["originalFs"] == 500.0
    assert result["parameters"]["resampled"] is True
    codes = {warning["code"] for warning in result["warnings"]}
    assert "short_record_padded" in codes
    assert "resampled" in codes
    assert "lead_out_of_distribution" in codes
    assert "detected_rpeaks" in codes
    assert len(result["beats"]) == result["parameters"]["nBeatsClassified"]

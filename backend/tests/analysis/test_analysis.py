"""AnalysisResult 组装、样本级验收与确定性。"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from eclipse_health_backend.analysis import AnalysisOptions, analyze
from eclipse_health_backend.analysis.features import MITBIH_CLASSES

MEASUREMENT_CODES = {
    "heart_rate_mean",
    "heart_rate_min",
    "heart_rate_max",
    "rr_mean",
    "sdnn",
    "rmssd",
    "pnn50",
    "qrs_duration",
    "pr_interval",
    "qt_interval",
    "qtc",
    "n_ratio",
    "svb_ratio",
    "veb_ratio",
    "f_ratio",
}


@pytest.mark.parametrize(
    ("fixture_name", "record"),
    [("analysis_100", "100"), ("analysis_200", "200"), ("analysis_208", "208")],
)
def test_result_schema(fixture_name, record, request) -> None:
    result = request.getfixturevalue(fixture_name)
    assert result["schema"] == "org.eclipsehealth.analysis/1"
    assert result["id"].startswith("ana_")
    assert result["recordId"] == f"rec_test_{record}"
    assert result["moduleId"] == "org.eclipsehealth.cardia"
    assert result["modelId"] == "cardia-2.0"
    assert result["status"] == "completed"
    assert result["task"] == "beat-classification"
    assert result["startedAt"].endswith("Z")
    assert result["completedAt"].endswith("Z")
    assert result["durationMs"] >= 0
    assert result["summary"].startswith("平均心率")
    assert result["beatsRef"] is None
    assert result["parameters"]["engine"] == "cardia"
    assert result["parameters"]["sequenceLength"] == 64
    assert len(result["provenance"]["modelSha256"]) == 64
    assert len(result["provenance"]["preprocessSha256"]) == 64


@pytest.mark.parametrize(
    ("fixture_name", "signal_name"),
    [("analysis_100", "signal_100"), ("analysis_200", "signal_200"),
     ("analysis_208", "signal_208")],
)
def test_beat_count_matches_annotations(fixture_name, signal_name, request) -> None:
    result = request.getfixturevalue(fixture_name)
    signal = request.getfixturevalue(signal_name)
    aami = [pos for pos, sym in signal.annotations if sym in MITBIH_CLASSES]
    assert abs(len(result["beats"]) - len(aami)) / len(aami) <= 0.02
    assert len(result["beats"]) == result["parameters"]["nBeatsClassified"]


def test_measurements(analysis_100) -> None:
    measurements = {item["code"]: item for item in analysis_100["measurements"]}
    assert MEASUREMENT_CODES <= set(measurements)
    assert measurements["heart_rate_mean"]["value"] == pytest.approx(75.5, abs=0.5)
    assert measurements["heart_rate_mean"]["unit"] == "bpm"
    for code in ("qrs_duration", "pr_interval", "qt_interval", "qtc"):
        assert measurements[code]["value"] is None
        assert measurements[code]["warnings"]
    ratios = sum(
        measurements[code]["value"]
        for code in ("n_ratio", "svb_ratio", "veb_ratio", "f_ratio")
    )
    assert ratios == pytest.approx(100.0, abs=0.05)


def test_probabilities_and_warnings(analysis_100) -> None:
    for beat in analysis_100["beats"][:50]:
        assert set(beat["probabilities"]) == {"N", "SVEB", "VEB", "F"}
        assert sum(beat["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)
        assert beat["label"] in {"N", "SVEB", "VEB", "F"}
        assert 0.0 <= beat["confidence"] <= 1.0
    codes = {warning["code"] for warning in analysis_100["warnings"]}
    assert "research_use_only" in codes
    assert "delineation_not_implemented" in codes
    assert "detected_rpeaks" not in codes


def test_quality_block(analysis_100) -> None:
    quality = analysis_100["quality"]
    assert 0.0 <= quality["score"] <= 1.0
    assert quality["level"] in {"good", "fair", "poor"}
    assert quality["segments"]
    assert isinstance(quality["warnings"], list)


def test_deterministic_output(signal_100) -> None:
    def fixed_id(prefix: str) -> str:
        return f"{prefix}_fixed"

    fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
    options = AnalysisOptions(
        record_id="rec_fixed",
        id_factory=fixed_id,
        clock=lambda: fixed_time,
    )
    first = analyze(signal_100, options)
    second = analyze(signal_100, options)
    assert first["beats"] == second["beats"]
    assert first["summary"] == second["summary"]
    assert [m["value"] for m in first["measurements"]] == [
        m["value"] for m in second["measurements"]
    ]
    assert first["quality"] == second["quality"]
    assert first["id"] == "ana_fixed"


def test_analyze_accepts_dicts(signal_100) -> None:
    signal_dict = {
        "samples": signal_100.samples[:3600],
        "fs": 360.0,
        "lead": "MLII",
        "digital": signal_100.digital[:3600],
        "annotations": [
            (pos, sym)
            for pos, sym in (signal_100.annotations or [])
            if pos < 3600
        ],
    }
    result = analyze(
        signal_dict,
        {"record_id": "rec_dict", "allow_short_record": True},
    )
    assert result["recordId"] == "rec_dict"
    assert result["parameters"]["nBeatsClassified"] > 0


def test_no_filename_in_provenance(analysis_100) -> None:
    provenance = analysis_100["provenance"]
    assert "record_name" not in provenance
    assert "100" not in provenance.get("signalSource", "")
    assert np.isfinite(analysis_100["parameters"]["meanConfidence"])

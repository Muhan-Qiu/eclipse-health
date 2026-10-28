"""与 V2 ``inference.predict_record`` 的逐搏概率对齐。"""

from __future__ import annotations

import numpy as np
import pytest

from eclipse_health_backend.analysis import AnalysisOptions, analyze, load_wfdb
from eclipse_health_backend.analysis.features import extract_104

CLASS_NAMES = ("N", "SVEB", "VEB", "F")


def test_probability_alignment(
    analysis_100,
    cardia_model,
    signal_100,
    samples_dir,
    model_dir,
    v2_feature_module,
    v2_inference_module,
) -> None:
    mlii, _, anns = v2_feature_module.read_wfdb_record(str(samples_dir / "100"))
    preprocess = v2_inference_module.load_preprocess(model_dir)
    rows, summary, reference_features, _, _ = v2_inference_module.predict_record(
        mlii, anns, preprocess, cardia_model.session, "onnx", record_name="100"
    )
    assert summary["n_beats"] == 2271
    assert summary["n_used"] == len(rows) == 2240

    ours = extract_104(signal_100.digital, signal_100.annotations)
    feature_diff = float(np.max(np.abs(ours.features - reference_features)))
    assert feature_diff < 1e-9

    beats = {beat["index"]: beat["probabilities"] for beat in analysis_100["beats"]}
    max_diff = 0.0
    for row in rows:
        probabilities = beats[row["beat_index"]]
        for name in CLASS_NAMES:
            max_diff = max(
                max_diff,
                abs(probabilities[name] - float(row[f"prob_{name}"])),
            )
    print(f"alignment: feature_diff={feature_diff:.3e} prob_max_diff={max_diff:.3e}")
    assert max_diff < 1e-4


def test_softmax_rows_sum_to_one(analysis_100) -> None:
    sums = np.asarray(
        [sum(beat["probabilities"].values()) for beat in analysis_100["beats"]]
    )
    assert np.allclose(sums, 1.0, atol=1e-5)


def test_tail_mode_drop_matches_v2_count(signal_100) -> None:
    result = analyze(
        signal_100,
        AnalysisOptions(record_id="rec_drop", tail_mode="drop"),
    )
    assert result["parameters"]["nBeatsClassified"] == 2240
    assert any(w["code"] == "beats_dropped" for w in result["warnings"])


@pytest.mark.parametrize("record", ["200", "208"])
def test_alignment_other_records(
    record,
    cardia_model,
    model_dir,
    samples_dir,
    v2_feature_module,
    v2_inference_module,
) -> None:
    signal = load_wfdb(samples_dir / record)
    result = analyze(
        signal,
        AnalysisOptions(record_id=f"rec_align_{record}", tail_mode="drop"),
    )
    mlii, _, anns = v2_feature_module.read_wfdb_record(str(samples_dir / record))
    preprocess = v2_inference_module.load_preprocess(model_dir)
    rows, _, _, _, _ = v2_inference_module.predict_record(
        mlii, anns, preprocess, cardia_model.session, "onnx", record_name=record
    )
    beats = {beat["index"]: beat["probabilities"] for beat in result["beats"]}
    max_diff = 0.0
    for row in rows:
        probabilities = beats[row["beat_index"]]
        for name in CLASS_NAMES:
            max_diff = max(
                max_diff,
                abs(probabilities[name] - float(row[f"prob_{name}"])),
            )
    assert max_diff < 1e-4

"""104 维特征：与 V2 参考实现逐位对齐。"""

from __future__ import annotations

import numpy as np

from eclipse_health_backend.analysis.features import extract_104


def test_features_match_v2(samples_dir, signal_100, v2_feature_module) -> None:
    mlii, _, anns = v2_feature_module.read_wfdb_record(str(samples_dir / "100"))
    reference, reference_pre, reference_labels = v2_feature_module.extract_104(
        mlii, anns
    )

    ours = extract_104(signal_100.digital, signal_100.annotations)
    assert ours.features.shape == reference.shape == (2271, 104)
    assert float(np.max(np.abs(ours.features - reference))) < 1e-9
    assert np.array_equal(ours.pre_r, reference_pre)
    assert np.array_equal(ours.labels, reference_labels)


def test_r_positions_match_valid_annotations(
    samples_dir, signal_100, v2_feature_module
) -> None:
    mlii, _, anns = v2_feature_module.read_wfdb_record(str(samples_dir / "100"))
    _, _, valid, r_pos = v2_feature_module.build_beats(mlii, anns)
    expected = r_pos[valid == 1][:2271]
    ours = extract_104(signal_100.digital, signal_100.annotations)
    assert np.array_equal(ours.r_positions, expected)


def test_lbp_histogram_sums(signal_100) -> None:
    features = extract_104(signal_100.digital, signal_100.annotations)
    lbp = features.features[:, 8:67]
    # 180 点窗、8 邻域：每个位置贡献 1，共 172 个位置。
    assert np.allclose(lbp.sum(axis=1), 172.0)


def test_features_are_finite(signal_100) -> None:
    features = extract_104(signal_100.digital, signal_100.annotations)
    assert np.isfinite(features.features).all()


def test_empty_annotations(signal_100) -> None:
    features = extract_104(signal_100.digital, [])
    assert features.features.shape == (0, 104)
    assert len(features) == 0

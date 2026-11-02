"""104 维特征：与 V2 参考实现逐位对齐。"""

from __future__ import annotations

import time

import numpy as np

from eclipse_health_backend.analysis.features import compute_rr_intervals, extract_104


def _brute_force_global_r(r: np.ndarray, pre_r: np.ndarray) -> np.ndarray:
    """参考实现的 O(n²) global_R，仅用于验证向量化结果逐位一致。"""
    n = len(r)
    out = np.zeros(n)
    if n == 0:
        return out
    out[0] = pre_r[0]
    for i in range(1, n):
        num, total = 0, 0.0
        for j in range(i):
            if (r[i] - r[j]) < 108000:
                total += pre_r[j]
                num += 1
        out[i] = total / float(max(num, 1))
    return out


def test_global_rr_matches_bruteforce() -> None:
    rng = np.random.default_rng(7)
    # 覆盖 5 分钟窗口边界、重复 RR、稀疏 R 峰等情况。
    positions = np.cumsum(rng.integers(120, 1400, size=400)).astype(float)
    intervals = compute_rr_intervals(positions)
    expected = _brute_force_global_r(positions, intervals.pre_R)
    assert np.allclose(intervals.global_R, expected, rtol=0, atol=1e-12)


def test_global_rr_window_boundary_is_exclusive() -> None:
    # 参考实现用严格小于：恰好相差 108000 的 R 峰不能计入窗口。
    positions = np.array([0.0, 108000.0, 108001.0, 216000.0])
    intervals = compute_rr_intervals(positions)
    expected = _brute_force_global_r(positions, intervals.pre_R)
    assert np.array_equal(intervals.global_R, expected)


def test_global_rr_is_linear_for_long_records() -> None:
    # 长记录（10 万搏）在 O(n²) 实现下需要数十亿次循环；这里应远低于 2 秒。
    positions = np.arange(100_000, dtype=float) * 300.0
    started = time.perf_counter()
    intervals = compute_rr_intervals(positions)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    assert intervals.global_R.shape == positions.shape
    assert np.all(np.isfinite(intervals.global_R))



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

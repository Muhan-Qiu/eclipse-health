"""104 维逐搏特征。

移植自 ``V2/发布预权重与评分信息/推理代码/feature_extract.py``（只读参考），
保留原算法的边界处理：±20 采样点局部 R 峰修正、±90 采样点窗、
双次中值滤波去基线、AAMI 四类映射、无效心搏丢弃。
数值必须与参考实现逐位对齐，对齐测试见 ``backend/tests/analysis``。
"""

from __future__ import annotations

import operator
from dataclasses import dataclass

import numpy as np
import pywt
import scipy.stats
from scipy.signal import medfilt

WINL = WINR = 90
SIZE_RR_MAX = 20
FS = 360

MITBIH_CLASSES = ["N", "L", "R", "e", "j", "A", "a", "J", "S", "V", "E", "F"]
AAMI_CLASSES = [
    ["N", "L", "R"],
    ["A", "a", "J", "S", "e", "j"],
    ["V", "E"],
    ["F"],
]

FEATURE_NAMES = (
    [
        "pre_R",
        "post_R",
        "local_R",
        "global_R",
        "norm_pre_R",
        "norm_post_R",
        "norm_local_R",
        "norm_global_R",
    ]
    + [f"u-lbp_{i:02d}" for i in range(59)]
    + [f"wvlt_{i:02d}" for i in range(23)]
    + [f"HOS_{i:02d}" for i in range(10)]
    + [f"myMorph_{i:02d}" for i in range(4)]
)
FEATURE_DIM = len(FEATURE_NAMES)

UNIFORM_PATTERN_LIST = np.array(
    [
        0,
        1,
        2,
        3,
        4,
        6,
        7,
        8,
        12,
        14,
        15,
        16,
        24,
        28,
        30,
        31,
        32,
        48,
        56,
        60,
        62,
        63,
        64,
        96,
        112,
        120,
        124,
        126,
        127,
        128,
        129,
        131,
        135,
        143,
        159,
        191,
        192,
        193,
        195,
        199,
        207,
        223,
        224,
        225,
        227,
        231,
        239,
        240,
        241,
        243,
        247,
        248,
        249,
        251,
        252,
        253,
        254,
        255,
    ]
)
_UNIFORM_LUT = np.full(256, 58, dtype=np.int64)
for _i, _p in enumerate(UNIFORM_PATTERN_LIST):
    _UNIFORM_LUT[int(_p)] = _i


@dataclass
class FeatureSet:
    """一维特征矩阵与逐搏元数据，行一一对应。"""

    features: np.ndarray  # [n, 104]，未标准化
    pre_r: np.ndarray  # [n]，当前搏动之前的 RR 间期（采样点）
    labels: np.ndarray  # [n]，AAMI 0=N 1=SVEB 2=VEB 3=F
    r_positions: np.ndarray  # [n]，修正后的 R 峰采样点

    def __len__(self) -> int:
        return int(self.features.shape[0])


@dataclass
class RRIntervals:
    pre_R: np.ndarray
    post_R: np.ndarray
    local_R: np.ndarray
    global_R: np.ndarray


def compute_rr_intervals(r_poses: np.ndarray) -> RRIntervals:
    """与参考实现 ``compute_RR_intervals`` 数值一致（含边界补齐）。

    预分配数组替代参考实现的 ``np.append`` 循环：结果逐位相同，
    但长记录下不再产生 O(n²) 的临时数组。
    """
    r = np.asarray(r_poses, dtype=float).ravel()
    n = len(r)
    if n == 0:
        empty = np.array([])
        return RRIntervals(empty, empty, empty, empty)
    if n == 1:
        zero = np.array([0.0])
        return RRIntervals(zero, zero.copy(), zero.copy(), zero.copy())

    pre_r = np.zeros(n)
    post_r = np.zeros(n)
    if n == 2:
        pre_r[1] = r[1] - r[0]
        post_r[0] = post_r[1] = r[1] - r[0]
    else:
        post_r[0] = r[1] - r[0]
        for i in range(1, n - 1):
            pre_r[i] = r[i] - r[i - 1]
            post_r[i] = r[i + 1] - r[i]
        pre_r[0] = pre_r[1]
        pre_r[n - 1] = r[-1] - r[-2]
        post_r[n - 1] = post_r[n - 2]

    local_r = np.zeros(n)
    for i in range(n):
        num, avg_val = 0, 0.0
        for j in range(-9, 1):
            if j + i >= 0:
                avg_val += pre_r[i + j]
                num += 1
        local_r[i] = avg_val / float(num)

    global_r = np.zeros(n)
    global_r[0] = pre_r[0]
    # 参考实现是 O(n²)：对每个 i 扫描 [0, i) 内 5 分钟窗口里的 pre_R。
    # R 峰位置单调递增，窗口起点可用二分定位，再做前缀和 → O(n log n)。
    # 非单调输入（理论上不该出现）回退到逐项实现，保证数值完全一致。
    if n > 1:
        if np.all(np.diff(r) >= 0):
            window = 108000.0
            starts = np.searchsorted(r, r - window, side="right")
            prefix = np.concatenate(([0.0], np.cumsum(pre_r)))
            indices = np.arange(n)
            counts = indices - starts
            sums = prefix[indices] - prefix[starts]
            global_r = np.divide(
                sums,
                np.maximum(counts, 1),
                out=np.zeros(n, dtype=np.float64),
                where=counts > 0,
            )
            global_r[0] = pre_r[0]
        else:
            for i in range(1, n):
                num, avg_val = 0, 0.0
                for j in range(i):
                    if (r[i] - r[j]) < 108000:
                        avg_val += pre_r[j]
                        num += 1
                global_r[i] = avg_val / float(max(num, 1))

    return RRIntervals(pre_r, post_r, local_r, global_r)


def compute_wavelet_descriptor(beat: np.ndarray, family: str = "db1", level: int = 3):
    coeffs = pywt.wavedec(beat, pywt.Wavelet(family), level=level)
    return coeffs[0]


def compute_my_own_descriptor(
    beat: np.ndarray, win_l: int = WINL, win_r: int = WINR
) -> np.ndarray:
    r_pos = int((win_l + win_r) / 2)
    r_value = beat[r_pos]
    my_morph = np.zeros(4)
    x_values = np.zeros(4)
    y_values = np.zeros(4)
    x_values[0], y_values[0] = max(enumerate(beat[0:40]), key=operator.itemgetter(1))
    x_values[1], y_values[1] = min(enumerate(beat[75:85]), key=operator.itemgetter(1))
    x_values[2], y_values[2] = min(enumerate(beat[95:105]), key=operator.itemgetter(1))
    x_values[3], y_values[3] = max(enumerate(beat[150:180]), key=operator.itemgetter(1))
    x_values[1] += 75
    x_values[2] += 95
    x_values[3] += 150

    x_max, x_min = max(x_values), min(x_values)
    y_max = max(np.append(y_values, r_value))
    y_min = min(np.append(y_values, r_value))
    r_pos_n = (r_pos - x_min) / (x_max - x_min)
    r_value_n = (r_value - y_min) / (y_max - y_min)
    for n in range(4):
        x_values[n] = (x_values[n] - x_min) / (x_max - x_min)
        y_values[n] = (y_values[n] - y_min) / (y_max - y_min)
        my_morph[n] = np.linalg.norm([r_pos_n - x_values[n], r_value_n - y_values[n]])
    my_morph[np.isnan(my_morph)] = 0.0
    return my_morph


def compute_hos_descriptor(
    beat: np.ndarray, n_intervals: int = 6, lag: int = 30
) -> np.ndarray:
    """单搏 HOS；保留 scipy 口径（skew bias=True，kurtosis fisher=False）。"""
    hos_b = np.zeros((n_intervals - 1) * 2)
    for i in range(n_intervals - 1):
        pose = lag * (i + 1)
        interval = beat[(pose - (lag // 2)) : (pose + (lag // 2))]
        hos_b[i] = scipy.stats.skew(interval, 0, True)
        if np.isnan(hos_b[i]):
            hos_b[i] = 0.0
        hos_b[(n_intervals - 1) + i] = scipy.stats.kurtosis(interval, 0, False, True)
        if np.isnan(hos_b[(n_intervals - 1) + i]):
            hos_b[(n_intervals - 1) + i] = 0.0
    return hos_b


def compute_hos_descriptor_batch(
    beats: np.ndarray, n_intervals: int = 6, lag: int = 30
) -> np.ndarray:
    """批量版，逐元素与 ``compute_hos_descriptor`` 一致。"""
    beats = np.asarray(beats, dtype=np.float64)
    half = lag // 2
    intervals = [
        beats[:, lag * (i + 1) - half : lag * (i + 1) + half]
        for i in range(n_intervals - 1)
    ]
    x = np.stack(intervals, axis=1)
    d = x - x.mean(axis=-1, keepdims=True)
    var = (d**2).mean(axis=-1)
    std = np.sqrt(var)
    skew = np.zeros_like(var)
    nonzero = std > 0
    skew[nonzero] = (d[nonzero] ** 3).mean(axis=-1) / (std[nonzero] ** 3)
    kurt = np.zeros_like(var)
    var_ok = var > 0
    kurt[var_ok] = (d[var_ok] ** 4).mean(axis=-1) / (var[var_ok] ** 2)
    return np.concatenate([skew, kurt], axis=1)


def compute_uniform_lbp(signal: np.ndarray, neigh: int = 8) -> np.ndarray:
    """单搏 uniform LBP 直方图（59 桶）。"""
    hist = np.zeros(59, dtype=float)
    for i in range(neigh // 2, len(signal) - neigh // 2):
        pattern = np.zeros(neigh)
        offsets = list(range(-neigh // 2, 0)) + list(range(1, neigh // 2 + 1))
        for ind, n in enumerate(offsets):
            if signal[i] > signal[i + n]:
                pattern[ind] = 1
        pattern_id = int("".join(str(c) for c in pattern.astype(int)), 2)
        if pattern_id in UNIFORM_PATTERN_LIST:
            pattern_uniform_id = int(
                np.argwhere(UNIFORM_PATTERN_LIST == pattern_id)[0][0]
            )
        else:
            pattern_uniform_id = 58
        hist[pattern_uniform_id] += 1.0
    return hist


def compute_uniform_lbp_batch(beats: np.ndarray, neigh: int = 8) -> np.ndarray:
    """批量版，逐元素与 ``compute_uniform_lbp`` 一致。"""
    beats = np.asarray(beats, dtype=np.float64)
    half = neigh // 2
    core = beats[:, half : beats.shape[1] - half]
    pattern = np.zeros(core.shape, dtype=np.int64)
    offsets = list(range(-half, 0)) + list(range(1, half + 1))
    for bit, off in enumerate(offsets):
        neighbour = beats[:, half + off : beats.shape[1] - half + off]
        pattern |= (core > neighbour).astype(np.int64) << (neigh - 1 - bit)
    ids = _UNIFORM_LUT[pattern]
    hist = np.zeros((len(beats), 59), dtype=np.float64)
    for k in range(59):
        hist[:, k] = (ids == k).sum(axis=1)
    return hist


def build_beats(
    mlii: np.ndarray, anns: list[tuple[int, str]]
) -> tuple[list[np.ndarray], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """切搏 + 双次中值滤波去基线；返回 beats/labels/valid/r_pos/beat_positions。"""
    mlii = np.asarray(mlii, dtype=np.float64)
    baseline = medfilt(mlii, 71)
    baseline = medfilt(baseline, 215)
    mlii = mlii - baseline

    beats: list[np.ndarray] = []
    labels: list[int] = []
    valid: list[int] = []
    r_pos: list[int] = []
    beat_positions: list[int] = []
    n_samples = len(mlii)

    for pos0, sym in anns:
        pos = int(pos0)
        if SIZE_RR_MAX < pos < (n_samples - SIZE_RR_MAX):
            idx, _ = max(
                enumerate(mlii[pos - SIZE_RR_MAX : pos + SIZE_RR_MAX]),
                key=operator.itemgetter(1),
            )
            pos = (pos - SIZE_RR_MAX) + idx
        r_pos.append(pos)

        lab = -1
        if sym in MITBIH_CLASSES:
            for i, group in enumerate(AAMI_CLASSES):
                if sym in group:
                    lab = i
                    break
        if lab >= 0 and pos > WINL and pos < (n_samples - WINR):
            beats.append(mlii[pos - WINL : pos + WINR].copy())
            labels.append(lab)
            valid.append(1)
            beat_positions.append(pos)
        else:
            valid.append(0)

    return (
        beats,
        np.asarray(labels, np.int64),
        np.asarray(valid, np.int64),
        np.asarray(r_pos, np.int64),
        np.asarray(beat_positions, np.int64),
    )


def extract_104(mlii: np.ndarray, anns: list[tuple[int, str]]) -> FeatureSet:
    """原始数字量 + 标注 -> 104 维特征。

    ``anns`` 是 ``(采样点, MIT-BIH 符号)``；自动检测的 R 峰统一用 ``"N"``。
    """
    beats, labels, valid, _r_pos, beat_positions = build_beats(mlii, anns)
    if len(beats) == 0:
        return FeatureSet(
            np.zeros((0, FEATURE_DIM), np.float64),
            np.zeros(0, np.float64),
            np.zeros(0, np.int64),
            np.zeros(0, np.int64),
        )

    rr = compute_rr_intervals(_r_pos)
    rr_pre = rr.pre_R[valid == 1]
    rr_post = rr.post_R[valid == 1]
    rr_local = rr.local_R[valid == 1]
    rr_global = rr.global_R[valid == 1]

    n = min(len(beats), len(rr_pre))
    beats = beats[:n]
    labels = labels[:n]
    beat_positions = beat_positions[:n]
    rr_pre = rr_pre[:n]
    rr_post = rr_post[:n]
    rr_local = rr_local[:n]
    rr_global = rr_global[:n]

    f_rr = np.column_stack([rr_pre, rr_post, rr_local, rr_global])
    f_rr_norm = np.column_stack(
        [
            rr_pre / max(np.average(rr_pre), 1e-12),
            rr_post / max(np.average(rr_post), 1e-12),
            rr_local / max(np.average(rr_local), 1e-12),
            rr_global / max(np.average(rr_global), 1e-12),
        ]
    )

    beats_arr = np.asarray(beats, dtype=np.float64)
    f_lbp = compute_uniform_lbp_batch(beats_arr, 8)
    f_wav = np.vstack(
        [compute_wavelet_descriptor(b, "db1", 3) for b in beats_arr]
    )
    f_hos = compute_hos_descriptor_batch(
        beats_arr, 6, round((WINL + WINR) / 6)
    )
    f_morph = np.vstack(
        [compute_my_own_descriptor(b, WINL, WINR) for b in beats_arr]
    )

    features = np.column_stack([f_rr, f_rr_norm, f_lbp, f_wav, f_hos, f_morph])
    return FeatureSet(features, rr_pre, labels, beat_positions)

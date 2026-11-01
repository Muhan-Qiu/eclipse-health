"""Relay V1 模块的纯函数：采样率/导联校验、心搏窗口、Δt、softmax 与聚合。

不 import onnxruntime / wfdb，保证单元测试可以直接在核心 venv 运行。
窗口参数与 V1 ``train_mitbih.py`` 完全一致：R 峰前 0.25 s、后 0.40 s，360 Hz，
逐导联 z-score；Δt = 相邻 R 峰间隔 / DS1 训练集 RR 中位数。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

FS = 360.0
EXPECTED_LEADS = 2
WIN_BEFORE_SECONDS = 0.25
WIN_AFTER_SECONDS = 0.40
WIN_BEFORE = round(WIN_BEFORE_SECONDS * FS)
WIN_AFTER = round(WIN_AFTER_SECONDS * FS)
WINDOW_SAMPLES = WIN_BEFORE + WIN_AFTER
SEQ_LEN = 64
# V1 run_experiments.py 在 DS1 训练记录上取 RR 中位数（275/360 s）做 Δt 无量纲化。
DT_MEDIAN_SECONDS = 275.0 / FS
CLASSES = ["N", "SVEB", "VEB", "F", "Q"]
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"

# V1 的 AAMI EC57 五类映射：''/L/R/e/j -> N；A/a/J/S -> S；V/E -> V；F -> F；Q。
AAMI = {
    "N": "N", "L": "N", "R": "N", "e": "N", "j": "N",
    "A": "S", "a": "S", "J": "S", "S": "S",
    "V": "V", "E": "V",
    "F": "F",
    "/": "Q", "f": "Q", "Q": "Q",
}


class AdapterError(ValueError):
    """业务错误：``code`` 给模块 RPC 用，``status`` 对齐 HTTP 语义。"""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def validate_fs(fs: Any) -> float:
    try:
        value = float(fs)
    except (TypeError, ValueError) as exc:
        raise AdapterError("sampling_rate_mismatch", "采样率缺失或不是数值", 422) from exc
    if not math.isfinite(value) or value <= 0:
        raise AdapterError("sampling_rate_mismatch", "采样率必须是正数", 422)
    if abs(value - FS) > 1e-6:
        raise AdapterError(
            "sampling_rate_mismatch",
            f"Relay V1 在 {FS:.0f} Hz 训练，输入为 {value:g} Hz；请先重采样到 360 Hz",
            422,
        )
    return value


def _fill_nan(signal: np.ndarray) -> np.ndarray:
    filled = signal.copy()
    index = np.arange(filled.shape[0])
    for channel in range(filled.shape[1]):
        column = filled[:, channel]
        bad = np.isnan(column)
        if not bad.any():
            continue
        if bad.all():
            filled[:, channel] = 0.0
        else:
            column[bad] = np.interp(index[bad], index[~bad], column[~bad])
    return filled


def normalize_channels(
    signal: Any, fs: Any, lead_indices: Sequence[int] | None = None
) -> np.ndarray:
    """把任意 1/多导联信号整理成 [N, 2] float32；单导联复制成两路并丢弃多余导联。"""
    validate_fs(fs)
    array = np.asarray(signal, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, None]
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] == 0:
        raise AdapterError("invalid_signal", "信号必须是 [N] 或 [N, C] 的非空数组", 422)
    array = _fill_nan(array)

    if lead_indices is None:
        indices = list(range(min(EXPECTED_LEADS, array.shape[1])))
    else:
        indices = []
        for raw in lead_indices:
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise AdapterError("invalid_lead", "leadIndices 必须是整数数组", 400)
            if raw < 0 or raw >= array.shape[1]:
                raise AdapterError(
                    "invalid_lead", f"导联下标 {raw} 超出 0–{array.shape[1] - 1}", 400
                )
            if raw not in indices:
                indices.append(raw)
        if not indices:
            raise AdapterError("invalid_lead", "至少选择一个导联", 400)

    selected = array[:, indices]
    if selected.shape[1] == 1:
        selected = np.repeat(selected, EXPECTED_LEADS, axis=1)
    elif selected.shape[1] > EXPECTED_LEADS:
        selected = selected[:, :EXPECTED_LEADS]
    return np.ascontiguousarray(selected, dtype=np.float32)


def extract_beats(
    signal: Any,
    rpeaks: Sequence[int],
    fs: Any,
    lead_indices: Sequence[int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """按 V1 口径切出心搏窗口，返回 ``beats [n, 2, 234]`` 与 ``positions [n]``。"""
    channels = normalize_channels(signal, fs, lead_indices)
    length = channels.shape[0]
    beats: list[np.ndarray] = []
    positions: list[int] = []
    for raw in rpeaks:
        if isinstance(raw, bool) or not isinstance(raw, (int, np.integer)):
            raise AdapterError("invalid_signal", "R 峰位置必须是整数采样下标", 422)
        peak = int(raw)
        start, stop = peak - WIN_BEFORE, peak + WIN_AFTER
        if start < 0 or stop > length:
            continue
        segment = channels[start:stop].T.copy()
        mean = segment.mean(axis=1, keepdims=True)
        std = segment.std(axis=1, keepdims=True) + np.float32(1e-6)
        beats.append((segment - mean) / std)
        positions.append(peak)
    if not beats:
        raise AdapterError(
            "too_few_beats",
            f"有效心搏窗口为 0 个（R 峰前后 {WIN_BEFORE}/{WIN_AFTER} 个采样点必须在记录内）",
            422,
        )
    return np.stack(beats).astype(np.float32), np.asarray(positions, dtype=np.int64)


def rr_seconds(positions: Sequence[int], fs: Any = FS) -> np.ndarray:
    """相邻心搏 RR（秒）；最后一个心搏补 0，与 V1 ``build_split`` 一致。"""
    validate_fs(fs)
    pos = np.asarray(positions, dtype=np.float64)
    rr = np.zeros(pos.size, dtype=np.float32)
    if pos.size > 1:
        rr[:-1] = ((pos[1:] - pos[:-1]) / float(fs)).astype(np.float32)
    return rr


def dt_from_positions(positions: Sequence[int], fs: Any = FS) -> np.ndarray:
    """Δt = RR / DS1 训练中位数（275/360 s）。"""
    return (rr_seconds(positions, fs) / np.float32(DT_MEDIAN_SECONDS)).astype(np.float32)


def chunk_sequences(
    beats: np.ndarray, positions: Sequence[int], seq_len: int = SEQ_LEN
) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """每条记录内连续、非重叠地切成 64 搏序列；末尾不足的丢弃（V1 同口径）。"""
    count = int(beats.shape[0])
    if count < seq_len:
        raise AdapterError(
            "too_few_beats",
            f"序列模型需要至少 {seq_len} 个连续心搏，当前只有 {count} 个",
            422,
        )
    dt = dt_from_positions(positions)
    return [
        (start, beats[start:start + seq_len], dt[start:start + seq_len])
        for start in range(0, count - seq_len + 1, seq_len)
    ]


def softmax(logits: Any) -> np.ndarray:
    array = np.asarray(logits, dtype=np.float64)
    if array.size == 0:
        raise AdapterError("invalid_output", "模型输出为空", 500)
    shifted = array - np.max(array, axis=-1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / np.sum(exponent, axis=-1, keepdims=True)


def aggregate(probabilities: Any, classes: Sequence[str] = CLASSES) -> dict[str, Any]:
    """对逐搏概率取均值/argmax 计数，返回可直接 JSON 化的摘要。"""
    probs = np.asarray(probabilities, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[0] == 0 or probs.shape[1] != len(classes):
        raise AdapterError("invalid_output", "概率矩阵形状与类别数不一致", 500)
    mean = probs.mean(axis=0)
    predicted = probs.argmax(axis=1)
    counts = np.bincount(predicted, minlength=len(classes))
    dominant = int(mean.argmax())
    return {
        "classes": list(classes),
        "probabilities": [round(float(value), 6) for value in mean],
        "counts": {name: int(counts[index]) for index, name in enumerate(classes)},
        "predictedClass": str(classes[dominant]),
        "confidence": round(float(mean[dominant]), 4),
        "scoredBeats": int(probs.shape[0]),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def validate_model_index(index: Any) -> list[dict[str, Any]]:
    """校验 models/index.json 的最小形状，并按分数降序返回模型列表。"""
    if not isinstance(index, dict) or not isinstance(index.get("models"), list):
        raise AdapterError("index_invalid", "models/index.json 缺少 models 数组", 500)
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in index["models"]:
        if not isinstance(entry, dict):
            raise AdapterError("index_invalid", "models[] 条目必须是对象", 500)
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            raise AdapterError("index_invalid", "模型 id 缺失或重复", 500)
        seen.add(model_id)
        group = entry.get("class")
        if group not in {"ours", "baseline"}:
            raise AdapterError("index_invalid", f"模型 {model_id} 的 class 非法", 500)
        if entry.get("metric") != "macro_f1":
            raise AdapterError("index_invalid", f"模型 {model_id} 的 metric 必须是 macro_f1", 500)
        try:
            float(entry.get("score"))
        except (TypeError, ValueError) as exc:
            raise AdapterError("index_invalid", f"模型 {model_id} 的 score 非数值", 500) from exc
        if not isinstance(entry.get("file"), str) or "/" in entry["file"] or "\\" in entry["file"]:
            raise AdapterError("index_invalid", f"模型 {model_id} 的 file 必须是文件名", 500)
        models.append(entry)
    if not models:
        raise AdapterError("index_invalid", "models 为空", 500)
    models.sort(key=lambda item: (-float(item["score"]), str(item["id"])))
    return models


def assert_ours_above_baselines(models: Sequence[dict[str, Any]]) -> None:
    """精选口径：自研最低分必须高于基线最高分，否则索引不许上线。"""
    ours = [float(entry["score"]) for entry in models if entry.get("class") == "ours"]
    baselines = [float(entry["score"]) for entry in models if entry.get("class") == "baseline"]
    if not ours or not baselines:
        raise AdapterError("index_invalid", "ours/baseline 两组都必须非空", 500)
    if min(ours) <= max(baselines):
        raise AdapterError(
            "index_invalid",
            f"自研最低 {min(ours):.4f} 未高于基线最高 {max(baselines):.4f}",
            500,
        )

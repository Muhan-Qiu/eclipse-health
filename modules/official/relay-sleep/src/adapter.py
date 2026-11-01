"""Relay 睡眠分期的纯函数适配层：输入校验、softmax、类别映射、摘要。

不 import onnxruntime，保证 manifest/形状/摘要测试无需真实权重。
"""

from __future__ import annotations

from typing import Any

import numpy as np

CLASSES = ["W", "N1", "N2", "N3", "R"]
FEAT_DIM = 272
SEQ_LEN = 10
BASELINE_WINDOWS = 3
BASELINE_SAMPLES = 3000
MAX_BATCH = 512
MAX_SEQUENCE_BATCH = 64
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"


class AdapterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _numeric_array(values: Any, label: str) -> np.ndarray:
    if values is None:
        raise AdapterError("invalid_input", f"{label} 缺失")
    try:
        array = np.asarray(values)
    except (TypeError, ValueError) as exc:
        raise AdapterError("invalid_input", f"{label} 不是数值数组") from exc
    if array.dtype.kind not in "fiu":
        raise AdapterError("invalid_input", f"{label} 必须是数值数组")
    array = array.astype(np.float32, copy=False)
    if not np.all(np.isfinite(array)):
        raise AdapterError("invalid_input", f"{label} 含 NaN/Inf")
    return array


def validate_features(values: Any) -> np.ndarray:
    """接受 [T,272] 或 [B,T,272]，固定 T=10，返回连续 float32。"""
    array = _numeric_array(values, "features")
    if array.ndim == 2:
        array = array[None, ...]
    if array.ndim != 3:
        raise AdapterError("invalid_input", "features 必须是 [T,272] 或 [B,T,272]")
    batch, seq, dim = array.shape
    if dim != FEAT_DIM:
        raise AdapterError("invalid_input", f"features 最后一维必须是 {FEAT_DIM}，实际 {dim}")
    if seq != SEQ_LEN:
        raise AdapterError("invalid_input", f"features 时间步必须是 {SEQ_LEN}，实际 {seq}")
    if not 1 <= batch <= MAX_BATCH:
        raise AdapterError("invalid_input", f"batch 必须在 1..{MAX_BATCH}")
    return np.ascontiguousarray(array, dtype=np.float32)


def validate_dt(values: Any, batch: int) -> np.ndarray:
    """接受 None/[T]/[B,T]/[B,T,1]，返回 [B,T,1]；缺省为 1（与训练一致）。"""
    if values is None:
        return np.ones((batch, SEQ_LEN, 1), dtype=np.float32)
    array = _numeric_array(values, "dt")
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim == 2:
        array = array[..., None]
    if array.ndim != 3 or array.shape[2] != 1:
        raise AdapterError("invalid_input", "dt 必须是 [T]、[B,T] 或 [B,T,1]")
    if array.shape[:2] != (batch, SEQ_LEN):
        raise AdapterError("invalid_input", f"dt 形状必须是 [{batch},{SEQ_LEN},1]")
    if np.any(array <= 0):
        raise AdapterError("invalid_input", "dt 必须为正数")
    return np.ascontiguousarray(array, dtype=np.float32)


def validate_windows(values: Any, channels: int) -> np.ndarray:
    """基线模型输入：[3,C,3000] 或 [B,3,C,3000]。"""
    array = _numeric_array(values, "windows")
    if array.ndim == 3:
        array = array[None, ...]
    if array.ndim != 4:
        raise AdapterError("invalid_input", "windows 必须是 [3,C,3000] 或 [B,3,C,3000]")
    batch, windows, found_channels, samples = array.shape
    if windows != BASELINE_WINDOWS or found_channels != channels or samples != BASELINE_SAMPLES:
        raise AdapterError(
            "invalid_input",
            f"windows 形状必须是 [B,{BASELINE_WINDOWS},{channels},{BASELINE_SAMPLES}]",
        )
    if not 1 <= batch <= MAX_SEQUENCE_BATCH:
        raise AdapterError("invalid_input", f"batch 必须在 1..{MAX_SEQUENCE_BATCH}")
    return np.ascontiguousarray(array, dtype=np.float32)


def softmax(values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.shape[-1] != len(CLASSES):
        raise AdapterError("invalid_input", f"logits 最后一维必须是 {len(CLASSES)}")
    shifted = array - np.max(array, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


def summarize(logits: Any, unit: str) -> dict[str, Any]:
    """把 [N,5] logits 汇总为逐单元 argmax、计数、占比与多数类。"""
    array = np.asarray(logits, dtype=np.float64)
    if array.ndim < 2 or array.shape[-1] != len(CLASSES):
        raise AdapterError("invalid_input", f"logits 必须是 [...,{len(CLASSES)}]")
    flat = array.reshape(-1, len(CLASSES))
    probabilities = softmax(flat)
    predicted = probabilities.argmax(axis=1)
    total = int(predicted.size)
    counts = [int(np.sum(predicted == index)) for index in range(len(CLASSES))]
    proportions = [round(count / total, 4) for count in counts] if total else [0.0] * len(CLASSES)
    rows = [
        {
            "index": index,
            "stage": CLASSES[int(predicted[index])],
            "confidence": round(float(probabilities[index, predicted[index]]), 4),
        }
        for index in range(total)
    ]
    return {
        "unit": unit,
        "total": total,
        "counts": dict(zip(CLASSES, counts, strict=True)),
        "proportions": dict(zip(CLASSES, proportions, strict=True)),
        "majority": CLASSES[int(np.argmax(counts))] if total else None,
        rows_key(unit): rows,
    }


def rows_key(unit: str) -> str:
    return "perWindow" if unit == "window" else "perSequence"


def round_logits(logits: Any) -> list[Any]:
    array = np.asarray(logits, dtype=np.float64)
    return np.round(array, 6).tolist()


def empty_stats() -> dict[str, Any]:
    """模块尚无持久化记录时的空摘要，供 widget/页面渲染。"""
    return {
        "latest": {"stage": None, "confidence": 0.0},
        "labels": list(CLASSES),
        "counts": [0] * len(CLASSES),
        "stages": [],
        "hasData": False,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }

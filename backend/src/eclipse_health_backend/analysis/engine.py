"""分析结果组装。

``analyze(signal, options)`` 是 B2 ``analysis-model`` 模块的唯一入口：
输入 EcgSignal/dict，输出可 JSON 序列化的 ``AnalysisResult`` dict。
不依赖 FastAPI、数据库或模块系统。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from .features import MITBIH_CLASSES, extract_104
from .ids import rfc3339
from .ingest import load_wfdb
from .measurements import compute_measurements
from .model import CardiaModel, read_preprocess
from .quality import assess_quality
from .types import (
    DEFAULT_FEATURE_GAIN,
    SCHEMA_ANALYSIS,
    AnalysisOptions,
    EcgSignal,
    InsufficientBeatsError,
    coerce_options,
    coerce_signal,
)

ENGINE_VERSION = "1.0.0"
PIPELINE_NAME = "mondejar-104-v1"


def _warning(
    code: str,
    message: str,
    severity: str = "warning",
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "startSec": start_sec,
        "endSec": end_sec,
    }


def _merge_warnings(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            key = (item.get("code"), item.get("message"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _detect_rpeaks(signal: EcgSignal, method: str) -> tuple[np.ndarray, list[dict]]:
    """无标注时的 R 峰检测：neurokit2，失败再退 scipy。"""
    x = np.asarray(signal.samples, dtype=np.float64)
    fs = signal.fs
    warnings: list[dict] = []
    try:
        import neurokit2 as nk

        clean = nk.ecg_clean(x, sampling_rate=fs, method="neurokit")
        _, info = nk.ecg_peaks(clean, sampling_rate=fs, method=method)
        peaks = np.asarray(info["ECG_R_Peaks"], dtype=np.int64)
    except Exception as exc:  # noqa: BLE001 - 检测器异常不应中断主流程
        peaks = np.array([], dtype=np.int64)
        warnings.append(
            _warning(
                "rpeak_detector_fallback",
                f"neurokit2 检测失败（{type(exc).__name__}），改用 scipy",
                severity="info",
            )
        )

    if len(peaks) < 3:
        from scipy.signal import butter, find_peaks, sosfiltfilt

        sos = butter(3, [5.0, 20.0], btype="bandpass", fs=fs, output="sos")
        filtered = sosfiltfilt(sos, x - np.median(x))
        prominence = 0.3 * float(np.percentile(np.abs(filtered), 99))
        found, _ = find_peaks(
            np.abs(filtered),
            distance=max(1, int(0.25 * fs)),
            prominence=max(prominence, 1e-9),
        )
        peaks = np.asarray(found, dtype=np.int64)
        if len(peaks) >= 3:
            warnings.append(
                _warning(
                    "rpeak_detector_fallback",
                    "neurokit2 未找到足够 R 峰，已改用 scipy 峰值检测",
                    severity="info",
                )
            )

    peaks = peaks[(peaks >= 0) & (peaks < signal.n_samples)]
    if len(peaks) == 0:
        raise InsufficientBeatsError("未检测到 R 峰，请检查采样率、导联与信号质量")
    warnings.append(
        _warning(
            "detected_rpeaks",
            f"无专家标注，使用自动检测的 {len(peaks)} 个 R 峰；分类结果仅供参考",
        )
    )
    return peaks, warnings


def _resolve_rpeaks(
    signal: EcgSignal, options: AnalysisOptions
) -> tuple[list[tuple[int, str]], np.ndarray, str, list[dict]]:
    """优先专家标注；没有时自动检测。

    返回 (特征用标注, 质量用 R 峰, 来源, warnings)。
    特征必须拿到**全部**标注（含 '+'/'~' 等节律标记），因为参考实现的 RR 间期
    是在全部标注上算的；只用 AAMI 心搏会让 RR 特征与 V2 不一致。
    """
    if signal.annotations:
        beat_anns = [
            (pos, sym) for pos, sym in signal.annotations if sym in MITBIH_CLASSES
        ]
        if beat_anns:
            beat_positions = np.asarray([pos for pos, _ in beat_anns], dtype=np.int64)
            return signal.annotations, beat_positions, "annotation", []
    peaks, warnings = _detect_rpeaks(signal, options.rpeak_method)
    annotations = [(int(p), "N") for p in peaks]
    return annotations, peaks, "detected", warnings


def analyze(
    signal: EcgSignal | Mapping[str, Any],
    options: AnalysisOptions | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """对一条单导联 ECG 做质量评估、逐搏分类与测量。"""
    if options is None:
        raise ValueError("options 必须提供，且包含 record_id")
    sig = coerce_signal(signal)
    opts = coerce_options(options)

    started_at = opts.clock()
    started_perf = time.perf_counter()

    annotations, rpeaks_all, rpeak_source, rpeak_warnings = _resolve_rpeaks(
        sig, opts
    )
    quality = assess_quality(sig, rpeaks_all)

    digital = (
        sig.digital
        if sig.digital is not None
        else np.asarray(sig.samples, dtype=np.float64) * DEFAULT_FEATURE_GAIN
    )
    feature_set = extract_104(digital, annotations)
    n_beats = len(feature_set)
    if n_beats == 0:
        raise InsufficientBeatsError(
            "没有有效心搏（窗口越界或标注符号不在 AAMI 四类内）"
        )

    preprocess = read_preprocess(opts.model_dir)
    sequence_length = int(preprocess.get("sequence_length", 64))
    if n_beats < sequence_length and not opts.allow_short_record:
        raise InsufficientBeatsError(
            f"有效心搏只有 {n_beats} 个（<{sequence_length}），无法组成预测输入；"
            "短记录请显式设置 allow_short_record=True 以零填充"
        )

    model = CardiaModel(opts.model_dir)
    probs, covered = model.predict(
        feature_set.features,
        feature_set.pre_r,
        allow_short=opts.allow_short_record,
        tail_mode=opts.tail_mode,
    )
    labels = np.argmax(probs, axis=1)

    if opts.tail_mode == "drop":
        keep = covered
        probs = probs[keep]
        labels = labels[keep]
        pre_r = feature_set.pre_r[keep]
        r_positions = feature_set.r_positions[keep]
    else:
        pre_r = feature_set.pre_r
        r_positions = feature_set.r_positions
    n_used = len(labels)

    class_order = list(model.class_order)
    class_counts = {
        name: int(np.sum(labels == idx)) for idx, name in enumerate(class_order)
    }

    analysis_id = opts.analysis_id or opts.make_id("ana")
    measurements = compute_measurements(
        r_positions=r_positions,
        fs=sig.fs,
        class_counts=class_counts,
        n_beats=n_used,
        duration_sec=sig.duration_sec,
        quality_score=quality.score,
        record_id=opts.record_id,
        analysis_id=analysis_id,
        id_factory=opts.make_id,
    )

    beats = _build_beats(
        r_positions=r_positions,
        pre_r=pre_r,
        probs=probs,
        labels=labels,
        class_order=class_order,
        fs=sig.fs,
    )

    engine_warnings: list[dict[str, Any]] = [
        _warning(
            "research_use_only",
            "研究/教育用途，不构成医疗诊断；Cardia 2.0 在 MIT-BIH MLII 上训练",
            severity="info",
        ),
        _warning(
            "delineation_not_implemented",
            "未实现波形 delineation，QRS/PR/QT/QTc 暂不可用",
            severity="info",
        ),
    ]
    if sig.lead.upper() != "MLII":
        engine_warnings.append(
            _warning(
                "lead_out_of_distribution",
                f"当前导联为 {sig.lead}；模型在 MLII 上训练，形态特征对导联敏感",
            )
        )
    if n_beats < sequence_length:
        engine_warnings.append(
            _warning(
                "short_record_padded",
                f"有效心搏 {n_beats} 个（<{sequence_length}），已零填充到 "
                f"{sequence_length} 搏；短记录结果仅供参考",
            )
        )
    if opts.tail_mode == "drop" and n_used < n_beats:
        engine_warnings.append(
            _warning(
                "beats_dropped",
                f"末尾 {n_beats - n_used} 个心搏不足一个 {sequence_length} 搏窗口，"
                "已丢弃",
                severity="info",
            )
        )

    max_conf = float(np.max(probs, axis=1).mean()) if n_used else 0.0
    if n_used and max_conf < 0.60:
        engine_warnings.append(
            _warning(
                "low_confidence",
                f"平均逐搏置信度 {max_conf:.2f}，模型对该记录把握较低",
            )
        )

    if len(beats) > opts.max_inline_beats:
        dropped = len(beats) - opts.max_inline_beats
        beats = beats[: opts.max_inline_beats]
        engine_warnings.append(
            _warning(
                "beats_truncated",
                f"逐搏结果超过 {opts.max_inline_beats} 条，已截断 {dropped} 条；"
                "测量值仍基于全部心搏",
            )
        )

    warnings = _merge_warnings(
        sig.warnings, rpeak_warnings, quality.warnings, engine_warnings
    )

    completed_at = opts.clock()
    duration_ms = round((time.perf_counter() - started_perf) * 1000)
    rr_ms = np.diff(r_positions) / sig.fs * 1000.0
    heart_rate = float(60000.0 / np.mean(rr_ms)) if len(rr_ms) else None
    summary = _summary(heart_rate, class_counts, n_used)

    return {
        "schema": SCHEMA_ANALYSIS,
        "id": analysis_id,
        "recordId": opts.record_id,
        "moduleId": opts.module_id,
        "modelId": opts.model_id,
        "modelVersion": opts.model_version,
        "task": "beat-classification",
        "status": "completed",
        "startedAt": rfc3339(started_at),
        "completedAt": rfc3339(completed_at),
        "durationMs": duration_ms,
        "summary": summary,
        "quality": quality.to_dict(),
        "measurements": measurements,
        "beats": beats,
        "beatsRef": None,
        "annotations": [],
        "warnings": warnings,
        "parameters": {
            "engine": "cardia",
            "engineVersion": ENGINE_VERSION,
            "sequenceLength": sequence_length,
            "stride": int(preprocess.get("stride", sequence_length)),
            "classOrder": class_order,
            "dtMedian": float(preprocess["dt_median"]),
            "featurePipeline": PIPELINE_NAME,
            "featureInput": "digital" if sig.digital is not None else "mv*gain",
            "tailMode": opts.tail_mode,
            "rpeakSource": rpeak_source,
            "lead": sig.lead,
            "originalFs": sig.original_fs,
            "resampled": sig.resampled,
            "allowShortRecord": opts.allow_short_record,
            "nBeatsDetected": n_beats,
            "nBeatsClassified": n_used,
            "meanConfidence": round(max_conf, 4),
            "qualityMetrics": quality.metrics,
        },
        "provenance": {
            "preprocess": "cardia-v2",
            "preprocessVersion": "2.0",
            "preprocessFile": model.info.preprocess_path.name,
            "preprocessSha256": model.info.preprocess_sha256,
            "modelFile": model.info.model_path.name,
            "modelSha256": model.info.model_sha256,
            "signalSource": sig.source,
            "rpeakSource": rpeak_source,
            "engine": f"eclipse-health-backend/analysis@{ENGINE_VERSION}",
        },
    }


def _build_beats(
    *,
    r_positions: np.ndarray,
    pre_r: np.ndarray,
    probs: np.ndarray,
    labels: np.ndarray,
    class_order: list[str],
    fs: float,
) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    for idx in range(len(labels)):
        probabilities = {
            class_order[k]: round(float(probs[idx, k]), 6)
            for k in range(len(class_order))
        }
        beats.append(
            {
                "index": idx,
                "rPeakSample": int(r_positions[idx]),
                "label": class_order[int(labels[idx])],
                "confidence": round(float(np.max(probs[idx])), 6),
                "rrPrevMs": round(float(pre_r[idx]) / fs * 1000.0),
                "probabilities": probabilities,
            }
        )
    return beats


def _summary(
    heart_rate: float | None, class_counts: dict[str, int], n_beats: int
) -> str:
    total = max(int(n_beats), 1)
    parts = [
        f"{name} {class_counts.get(name, 0) / total * 100:.1f}%"
        for name in ("N", "SVEB", "VEB", "F")
    ]
    if heart_rate is None:
        return "平均心率不可用 · " + " · ".join(parts)
    return f"平均心率 {heart_rate:.0f} bpm · " + " · ".join(parts)


__all__ = ["analyze", "load_wfdb"]

"""通用 ONNX 分析引擎执行器（A3）。

加载 ``analysis-model`` 模块自带、经过 sha256 校验的单个 ONNX 文件，按
manifest 的受控 ``preprocess`` / ``input`` / ``output`` 字段做推理，并映射成
合法的 ``AnalysisResult``。

支持两类预处理管线：

- **窗口分类（默认）**：按 ``windowSamples`` / ``strideSamples`` 在整段信号上
  滑窗，适用于 2/3 维输入的简单模型；
- **``relay-v1-beat-window``**：按 V1 ``train_mitbih.py`` 的口径处理
  R 峰切窗（默认 R 前 90 / 后 144 点）、逐导联 z-score、单导联复制为双导联、
  64 搏序列和 ``dt`` 第二输入。适用于 ``input.mode = sequence|beat`` 的
  逐搏分类模型（relay-ecg 的 7 个模型）。

任何形状/类型不匹配都抛 ``OnnxEngineError``（落库为 ``engine_error``），
不静默返回空结果，也不把底层 ``ValueError`` 直接暴露给用户。模型级分类不是
逐搏诊断，结果里固定带非诊断警告。

限制：只支持 ONNX Runtime 可加载的单文件模型；外部权重文件（external data）
不在本版范围。
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..analysis.ids import new_id, rfc3339
from ..analysis.measurements import compute_measurements
from ..analysis.quality import assess_quality
from ..analysis.types import SCHEMA_ANALYSIS, SCHEMA_MEASUREMENT, EcgSignal
from .engines import ModuleModelSpec

logger = logging.getLogger(__name__)

_ENGINE_VERSION = "1.1.0"
_ALLOWED_NORMALIZE = {"none", "zscore", "minmax"}
_ALLOWED_AGGREGATION = {"mean", "max"}
_RELAY_PIPELINE = "relay-v1-beat-window"
_RELAY_DEFAULT_FS = 360.0
_RELAY_DEFAULT_BEFORE = 90
_RELAY_DEFAULT_AFTER = 144
_RELAY_DEFAULT_SEQ_LEN = 64
_RELAY_DEFAULT_DT_MEDIAN = 275.0 / _RELAY_DEFAULT_FS
_MAX_BEAT_BATCH = 256

_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, Any] = {}


class OnnxEngineError(Exception):
    """模块 ONNX 引擎的业务错误；落库为 ``status=failed`` + ``error``。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "engine_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


# ---------------------------------------------------------------------- 会话
def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def _session_for(spec: ModuleModelSpec) -> Any:
    """按模型文件哈希缓存 ORT 会话；从字节加载以规避 Windows 中文路径问题。"""
    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - 依赖已在 pyproject 中
        raise OnnxEngineError("缺少 onnxruntime 依赖") from exc

    intra = _int_env("EH_ONNX_INTRA_THREADS", 1)
    key = f"{spec.model_sha256}:{intra}"
    with _SESSION_LOCK:
        cached = _SESSIONS.get(key)
        if cached is not None:
            return cached
        try:
            blob = spec.model_path.read_bytes()
        except OSError as exc:
            raise OnnxEngineError("模型文件不可读") from exc
        if hashlib.sha256(blob).hexdigest() != spec.model_sha256:
            raise OnnxEngineError("模型文件校验失败，文件可能在安装后被修改")
        options = ort.SessionOptions()
        options.intra_op_num_threads = intra
        options.inter_op_num_threads = _int_env("EH_ONNX_INTER_THREADS", 1)
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.log_severity_level = 3
        # relay 序列模型的 batch 是符号维度；不固定为 1 时 ORT 要对上万节点做
        # 符号形状推导，k12 加载可能超过十分钟。与模块自身 worker 的做法一致。
        inputs = spec.model.get("input")
        if isinstance(inputs, dict) and str(inputs.get("mode") or "").lower() == "sequence":
            try:
                options.add_free_dimension_override_by_name("batch", 1)
            except Exception:
                logger.debug("free dimension override unsupported", exc_info=True)
        try:
            session = ort.InferenceSession(
                blob, sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise OnnxEngineError(f"ONNX 会话初始化失败：{exc}"[:300]) from exc
        _SESSIONS[key] = session
        return session


# ---------------------------------------------------------------------- 配置
def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _positive_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _declared_shape(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _shape_dim(shape: list[Any], index: int) -> int | None:
    """取静态维度；负数/符号维度返回 None。"""
    if not shape or index >= len(shape) or index < -len(shape):
        return None
    value = shape[index]
    return value if isinstance(value, int) and value > 0 else None


def _tensor_shape(spec: ModuleModelSpec, name: str) -> list[Any]:
    inputs = spec.model.get("input")
    inputs = inputs if isinstance(inputs, dict) else {}
    tensors = inputs.get("tensors")
    tensors = tensors if isinstance(tensors, dict) else {}
    tensor = tensors.get(name)
    tensor = tensor if isinstance(tensor, dict) else {}
    return _declared_shape(tensor.get("shape"))


def _relay_config(spec: ModuleModelSpec, input_shapes: dict[str, list[Any]]) -> dict[str, Any]:
    """解析 ``relay-v1-beat-window`` 管线参数；缺省值与 V1 训练脚本一致。"""
    pre = spec.model.get("preprocess")
    inputs = spec.model.get("input")
    pre = pre if isinstance(pre, dict) else {}
    inputs = inputs if isinstance(inputs, dict) else {}

    x_shape = input_shapes.get("x") or _tensor_shape(spec, "x")
    dt_shape = input_shapes.get("dt") or _tensor_shape(spec, "dt")
    mode = str(inputs.get("mode") or ("sequence" if len(x_shape) >= 4 else "beat")).lower()
    if mode not in {"sequence", "beat"}:
        raise OnnxEngineError(f"不支持的逐搏模型输入模式：{mode}")

    fs = (
        _positive_float(pre.get("fs"))
        or _positive_float(inputs.get("fs"))
        or _RELAY_DEFAULT_FS
    )
    before = _positive_int(inputs.get("windowBefore"))
    after = _positive_int(inputs.get("windowAfter"))
    if before is None:
        before = round(
            (_positive_float(pre.get("windowBeforeSeconds")) or 0.25) * fs
        )
    if after is None:
        after = round((_positive_float(pre.get("windowAfterSeconds")) or 0.40) * fs)
    window = _positive_int(inputs.get("windowSamples")) or _shape_dim(x_shape, -1)
    if window is None:
        window = before + after
    # 窗口长度是模型输入的事实源；前后比例以 window 为准修正 after。
    if window != before + after:
        fixed_after = window - before
        if fixed_after <= 0:
            raise OnnxEngineError(
                f"模型窗口 {window} 与前缀 {before} 不匹配，无法切出心搏"
            )
        after = fixed_after

    leads = _positive_int(inputs.get("leads"))
    if leads is None and len(x_shape) >= 2:
        leads = _shape_dim(x_shape, -2)
    if leads is None and mode == "beat":
        leads = _shape_dim(x_shape, 1)
    if leads is None:
        leads = 1

    seq_len = _positive_int(inputs.get("beatsPerWindow"))
    if seq_len is None and mode == "sequence" and len(x_shape) >= 4:
        seq_len = _shape_dim(x_shape, 1)
    if seq_len is None and mode == "sequence" and dt_shape:
        seq_len = _shape_dim(dt_shape, -1)
    if seq_len is None:
        seq_len = _RELAY_DEFAULT_SEQ_LEN

    zscore = str(pre.get("zscore") or "").strip().lower() == "per-lead" or bool(
        inputs.get("zscorePerLead")
    )
    dt_median = (
        _positive_float(inputs.get("dtMedianSeconds"))
        or _positive_float(pre.get("dtMedianSeconds"))
        or _RELAY_DEFAULT_DT_MEDIAN
    )
    return {
        "kind": "relay",
        "pipeline": str(pre.get("pipeline") or _RELAY_PIPELINE),
        "mode": mode,
        "fs": fs,
        "leads": leads,
        "windowSamples": window,
        "windowBefore": before,
        "windowAfter": after,
        "beatsPerWindow": seq_len,
        "zscore": zscore,
        "dtMedianSeconds": dt_median,
        "xShape": x_shape,
        "dtShape": dt_shape,
        "hasDt": "dt" in (inputs.get("tensors") or {}),
    }


def _preprocess_config(
    spec: ModuleModelSpec,
    input_shape: list[Any],
    input_shapes: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    pre = spec.model.get("preprocess")
    inputs = spec.model.get("input")
    pre = pre if isinstance(pre, dict) else {}
    inputs = inputs if isinstance(inputs, dict) else {}

    pipeline = str(pre.get("pipeline") or "").strip()
    mode = str(inputs.get("mode") or "").strip().lower()
    if pipeline == _RELAY_PIPELINE or (
        mode in {"sequence", "beat"} and isinstance(inputs.get("tensors"), dict)
    ):
        return _relay_config(spec, input_shapes or {})

    normalize = str(pre.get("normalize") or "none").strip().lower()
    if normalize not in _ALLOWED_NORMALIZE:
        raise OnnxEngineError(f"不支持的预处理 normalize：{normalize}")

    window = _positive_int(pre.get("windowSamples")) or _positive_int(
        inputs.get("windowSamples")
    )
    if window is None and input_shape:
        last = input_shape[-1]
        window = last if isinstance(last, int) and last > 0 else None
    if window is None:
        raise OnnxEngineError("模型未声明 windowSamples，且输入形状不是静态")

    stride = _positive_int(pre.get("strideSamples")) or window
    fs = _positive_float(pre.get("samplingRate")) or _positive_float(
        pre.get("fs")
    ) or _positive_float(inputs.get("fs"))
    leads = inputs.get("leads")
    lead = str(pre.get("lead") or (leads[0] if isinstance(leads, list) and leads else ""))
    channels = _positive_int(pre.get("channels")) or 1
    if channels == 1 and len(input_shape) == 3:
        middle = input_shape[1]
        if isinstance(middle, int) and middle > 1:
            channels = middle
    if channels == 1:
        declared = _positive_int(inputs.get("leads"))
        if declared is not None:
            channels = declared

    return {
        "kind": "window",
        "pipeline": "window",
        "lead": lead,
        "samplingRate": fs,
        "windowSamples": window,
        "strideSamples": stride,
        "normalize": normalize,
        "channels": channels,
    }


def _output_config(spec: ModuleModelSpec) -> dict[str, Any]:
    output = spec.model.get("output")
    output = output if isinstance(output, dict) else {}
    kind = str(output.get("type") or ("classification" if output.get("classes") else ""))
    if kind != "classification":
        raise OnnxEngineError(f"暂不支持的输出类型：{kind or '未声明'}")
    classes = output.get("classes")
    if (
        not isinstance(classes, list)
        or not classes
        or not all(isinstance(item, str) and item for item in classes)
    ):
        raise OnnxEngineError("classification 输出必须声明非空 classes 数组")
    aggregation = str(output.get("aggregation") or "mean").strip().lower()
    if aggregation not in _ALLOWED_AGGREGATION:
        raise OnnxEngineError(f"不支持的 aggregation：{aggregation}")
    return {
        "type": kind,
        "classes": list(classes),
        "aggregation": aggregation,
        "multiOutput": output,
    }


# ---------------------------------------------------------------------- 通用预处理
def _resample(samples: np.ndarray, fs: float, target_fs: float) -> tuple[np.ndarray, bool]:
    if abs(fs - target_fs) < 1e-6:
        return samples, False
    from ..analysis.ingest import resample_signal

    resampled = resample_signal(
        EcgSignal(samples=samples, fs=fs, lead="unknown", source="record"),
        target_fs=target_fs,
    )
    return np.asarray(resampled.samples, dtype=np.float32), True


def _build_windows(
    samples: np.ndarray, window: int, stride: int, tail_mode: str
) -> tuple[np.ndarray, int]:
    """返回 ``(windows[n, window], 补齐的样本数)``；短信号按 tail_mode 处理。"""
    total = int(samples.size)
    if total < window:
        if tail_mode == "drop":
            raise OnnxEngineError(
                f"信号只有 {total} 个采样点，短于模型窗口 {window}（tailMode=drop）"
            )
        padded = np.zeros(window, dtype=np.float32)
        padded[:total] = samples
        return padded[None, :], window - total
    starts = list(range(0, total - window + 1, stride))
    windows = [samples[start : start + window] for start in starts]
    padded = 0
    remainder = total - (starts[-1] + window)
    if remainder > 0 and tail_mode == "pad":
        windows.append(samples[total - window : total])
        padded = remainder
    return np.stack(windows).astype(np.float32), padded


def _normalize(windows: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return windows
    values = windows.astype(np.float64)
    if mode == "zscore":
        mean = values.mean(axis=1, keepdims=True)
        scale = values.std(axis=1, keepdims=True)
        scale[scale < 1e-9] = 1.0
        return ((values - mean) / scale).astype(np.float32)
    low = values.min(axis=1, keepdims=True)
    high = values.max(axis=1, keepdims=True)
    span = high - low
    span[span < 1e-9] = 1.0
    return ((values - low) / span).astype(np.float32)


def _dim_ok(dim: Any, expected: int) -> bool:
    if isinstance(dim, bool):
        return False
    if isinstance(dim, int):
        return dim == expected
    return True  # None 或符号维度


def _fit_input(
    windows: np.ndarray, shape: list[Any], channels: int, window: int
) -> np.ndarray:
    count = windows.shape[0]
    rank = len(shape)
    try:
        if rank == 2:
            last = shape[1]
            if _dim_ok(last, window):
                return windows
            if channels > 1:
                return np.repeat(windows[:, None, :], channels, axis=1).reshape(
                    count, window * channels
                )
            raise OnnxEngineError(f"模型输入特征维 {last} 与窗口长度 {window} 不匹配")
        if rank == 3:
            first, second = shape[1], shape[2]
            if _dim_ok(first, channels) and _dim_ok(second, window):
                return np.repeat(windows[:, None, :], channels, axis=1)
            if _dim_ok(first, window) and _dim_ok(second, channels):
                return np.repeat(windows[:, :, None], channels, axis=2)
            raise OnnxEngineError(
                f"模型输入形状 {shape} 与通道/窗口 {channels}/{window} 不匹配"
            )
    except OnnxEngineError:
        raise
    except (ValueError, TypeError) as exc:
        raise OnnxEngineError(
            f"模型输入形状 {shape} 与数据形状 {windows.shape} 不匹配：{exc}"
        ) from exc
    raise OnnxEngineError(f"仅支持 2/3 维输入，模型输入维度为 {rank}")


# ---------------------------------------------------------------------- 逐搏预处理
def _prepare_channels(samples: np.ndarray, leads: int) -> np.ndarray:
    """把 1D/2D 信号整理成 ``[N, leads]``；单导联复制到全部通道。"""
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, None]
    elif array.ndim == 2:
        # 兼容 [C, N] 的输入；通道数通常很小。
        if array.shape[0] < array.shape[1] and array.shape[0] <= 4:
            array = array.T
    else:
        raise OnnxEngineError(f"信号必须是 1D 或 2D 数组，当前维度为 {array.ndim}")
    if array.shape[0] == 0 or array.shape[1] == 0:
        raise OnnxEngineError("信号为空，无法按心搏分析", code="invalid_signal")
    if array.shape[1] < leads:
        repeats = int(np.ceil(leads / array.shape[1]))
        array = np.tile(array, (1, repeats))[:, :leads]
    elif array.shape[1] > leads:
        array = array[:, :leads]
    if not np.isfinite(array).all():
        array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    return np.ascontiguousarray(array, dtype=np.float32)


def _detect_rpeaks(signal: np.ndarray, fs: float) -> np.ndarray:
    """使用 WFDB 的 XQRS 检测 R 峰；失败时转成可读的业务错误。"""
    try:
        from wfdb.processing import xqrs_detect

        peaks = xqrs_detect(
            sig=np.asarray(signal, dtype=np.float32), fs=float(fs), verbose=False
        )
    except Exception as exc:
        raise OnnxEngineError(
            f"R 峰检测失败：{type(exc).__name__}: {exc}"[:300]
        ) from exc
    positions = np.asarray(peaks, dtype=np.int64)
    if positions.size == 0:
        raise OnnxEngineError(
            "未检测到 R 峰，无法按心搏分析", code="too_few_beats"
        )
    return positions


def _extract_beats(
    channels: np.ndarray, rpeaks: np.ndarray, before: int, after: int
) -> tuple[np.ndarray, np.ndarray]:
    """按 R 峰切出 ``[n, leads, window]`` 心搏窗口，丢弃越界心搏。"""
    length = int(channels.shape[0])
    beats: list[np.ndarray] = []
    positions: list[int] = []
    for raw in rpeaks:
        peak = int(raw)
        start, stop = peak - before, peak + after
        if start < 0 or stop > length:
            continue
        beats.append(channels[start:stop].T.copy())
        positions.append(peak)
    if not beats:
        raise OnnxEngineError(
            f"R 峰前后 {before}/{after} 个采样点必须在记录内，当前没有完整心搏",
            code="too_few_beats",
        )
    return np.stack(beats).astype(np.float32), np.asarray(positions, dtype=np.int64)


def _zscore_beats(beats: np.ndarray) -> np.ndarray:
    values = beats.astype(np.float64)
    mean = values.mean(axis=2, keepdims=True)
    scale = values.std(axis=2, keepdims=True)
    scale[scale < 1e-9] = 1.0
    return ((values - mean) / scale).astype(np.float32)


def _dt_from_positions(
    positions: np.ndarray, fs: float, dt_median: float
) -> np.ndarray:
    """Δt = RR（秒）/ 训练集 RR 中位数；最后一个心搏补 0，与 V1 一致。"""
    pos = np.asarray(positions, dtype=np.float64)
    rr = np.zeros(pos.size, dtype=np.float32)
    if pos.size > 1:
        rr[:-1] = ((pos[1:] - pos[:-1]) / float(fs)).astype(np.float32)
    return (rr / np.float32(dt_median)).astype(np.float32)


def _sequence_chunks(
    beats: np.ndarray,
    positions: np.ndarray,
    seq_len: int,
    fs: float,
    dt_median: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    count = int(beats.shape[0])
    if count < seq_len:
        raise OnnxEngineError(
            f"序列模型需要至少 {seq_len} 个连续心搏，当前只有 {count} 个",
            code="too_few_beats",
        )
    dt = _dt_from_positions(positions, fs, dt_median)
    return [
        (beats[start : start + seq_len], dt[start : start + seq_len])
        for start in range(0, count - seq_len + 1, seq_len)
    ]


def _resolve_tensor_names(
    input_meta: list[Any], has_dt: bool
) -> tuple[str, str | None]:
    names = [str(getattr(item, "name", "")) for item in input_meta if getattr(item, "name", "")]
    if not names:
        raise OnnxEngineError("模型没有可用输入")
    x_name = "x" if "x" in names else names[0]
    dt_name: str | None = None
    if "dt" in names:
        dt_name = "dt"
    elif has_dt and len(names) > 1:
        dt_name = names[1]
    return x_name, dt_name


def _input_shape_for(input_meta: list[Any], name: str) -> list[Any]:
    for item in input_meta:
        if str(getattr(item, "name", "")) == name:
            return _declared_shape(getattr(item, "shape", []) or [])
    return []


def _static_batch(shape: list[Any], default: int) -> int:
    value = _shape_dim(shape, 0)
    return value if value is not None else default


def _run_feed(session: Any, feed: dict[str, np.ndarray]) -> Any:
    try:
        return session.run(None, feed)[0]
    except Exception as exc:
        raise OnnxEngineError(f"ONNX 推理失败：{exc}"[:300]) from exc


# ---------------------------------------------------------------------- 推理
def _run(session: Any, input_name: str, data: np.ndarray, batch: int | None) -> Any:
    def _call(chunk: np.ndarray) -> Any:
        return _run_feed(session, {input_name: chunk.astype(np.float32)})

    if batch is None:
        return _call(data)
    chunks: list[np.ndarray] = []
    for start in range(0, len(data), batch):
        chunk = data[start : start + batch]
        keep = len(chunk)
        if keep < batch:
            # 静态 batch 的模型要求固定批大小。
            padded = np.zeros((batch, *data.shape[1:]), dtype=data.dtype)
            padded[:keep] = chunk
            chunk = padded
        result = np.asarray(_call(chunk))
        if result.ndim == 0:
            raise OnnxEngineError("模型输出是标量，无法按窗口分类")
        chunks.append(result[:keep])
    return chunks[0] if len(chunks) == 1 else np.concatenate(chunks, axis=0)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def _probabilities(raw: Any, classes: list[str]) -> np.ndarray:
    """把 ``[B, C]`` / ``[B, T, C]`` / ``[1, T, C]`` 输出统一成 ``[N, C]``。"""
    try:
        values = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise OnnxEngineError("模型输出不是数值张量") from exc
    count = len(classes)
    if values.ndim == 0:
        raise OnnxEngineError("模型输出是标量，无法分类")
    values = np.squeeze(values)
    if values.ndim == 0:
        values = values.reshape(1, 1)
    if values.ndim == 1:
        if values.size != count:
            raise OnnxEngineError(
                f"模型输出形状 {values.shape} 与类别数 {count} 不匹配"
            )
        values = values[None, :]
    else:
        if values.shape[-1] != count:
            if values.shape[0] == count:
                values = np.moveaxis(values, 0, -1)
            else:
                raise OnnxEngineError(
                    f"模型输出形状 {values.shape} 与类别数 {count} 不匹配"
                )
        values = values.reshape(-1, count)
    if not np.isfinite(values).all():
        raise OnnxEngineError("模型输出包含 NaN/Inf")
    looks_like_probs = bool(
        values.min() >= 0.0
        and np.allclose(values.sum(axis=1), 1.0, atol=1e-3)
    )
    return values if looks_like_probs else _softmax(values)


def _aggregate(probs: np.ndarray, mode: str) -> np.ndarray:
    if mode == "max":
        final = probs.max(axis=0)
        total = float(final.sum())
        return final / total if total > 0 else final
    return probs.mean(axis=0)


def _relay_summary(
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


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned[:48] or "class"


def _warning(code: str, message: str, severity: str = "warning") -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "startSec": None,
        "endSec": None,
    }


def _build_result(
    *,
    spec: ModuleModelSpec,
    record_id: str,
    analysis_id: str,
    classes: list[str],
    final: np.ndarray,
    warnings: list[dict[str, Any]],
    aggregation: str,
    duration_ms: int,
    started: datetime,
    completed_at: datetime,
    parameters: dict[str, Any],
    provenance: dict[str, Any],
    scored: int,
    window_seconds: float,
    quality: dict[str, Any] | None = None,
    extra_measurements: list[dict[str, Any]] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    if summary is None:
        summary = "模型级分类（非逐搏诊断）· " + " · ".join(
            f"{name} {float(value) * 100:.1f}%"
            for name, value in zip(classes, final, strict=True)
        )
    measurements = [
        {
            "schema": SCHEMA_MEASUREMENT,
            "id": new_id("msr"),
            "recordId": record_id,
            "analysisId": analysis_id,
            "code": f"{spec.module_id}.class_probability.{_slug(name)}",
            "label": f"{name} 概率",
            "value": round(float(value) * 100.0, 4),
            "unit": "%",
            "ucum": "",
            "range": {"startSec": 0, "endSec": round(float(window_seconds), 3)},
            "method": spec.model_id,
            "warnings": [],
        }
        for name, value in zip(classes, final, strict=True)
    ]
    measurements.extend(extra_measurements or [])
    return {
        "schema": SCHEMA_ANALYSIS,
        "id": analysis_id,
        "recordId": record_id,
        "engine": spec.engine_id,
        "moduleId": spec.module_id,
        "modelId": spec.model_id,
        "modelVersion": spec.module_version,
        "task": str(spec.model.get("task") or "beat-classification"),
        "status": "completed",
        "startedAt": rfc3339(started),
        "completedAt": rfc3339(completed_at),
        "durationMs": duration_ms,
        "summary": summary,
        "quality": quality,
        "measurements": measurements,
        "beats": [],
        "beatsRef": None,
        "annotations": [],
        "warnings": warnings,
        "parameters": {
            "engine": spec.engine_id,
            "engineVersion": _ENGINE_VERSION,
            "modelFormat": "onnx",
            "classOrder": classes,
            "aggregation": aggregation,
            "windows": scored,
            **parameters,
        },
        "provenance": {
            "engine": f"eclipse-health-backend/analysis_service/onnx@{_ENGINE_VERSION}",
            "modelSource": f"module:{spec.module_id}",
            "moduleVersion": spec.module_version,
            "modelFile": spec.model_relative_path,
            "modelSha256": spec.model_sha256,
            **provenance,
        },
    }


class OnnxEngineRunner:
    """一个模块引擎的一次推理。无状态，可重复调用。"""

    def __init__(self, spec: ModuleModelSpec) -> None:
        self.spec = spec

    def analyze(
        self,
        *,
        record_id: str,
        analysis_id: str,
        samples: np.ndarray,
        fs: float,
        lead: str,
        tail_mode: str = "pad",
        started_at: datetime | None = None,
    ) -> dict[str, Any]:
        started = started_at or datetime.now(UTC)
        started_perf = time.perf_counter()

        if tail_mode not in {"pad", "drop"}:
            raise OnnxEngineError(f"不支持的 tailMode：{tail_mode}")

        session = _session_for(self.spec)
        input_meta = list(session.get_inputs())
        if not input_meta:
            raise OnnxEngineError("模型没有输入")
        input_shape = _declared_shape(getattr(input_meta[0], "shape", []) or [])
        input_shapes = {
            str(getattr(item, "name", "")): _declared_shape(
                getattr(item, "shape", []) or []
            )
            for item in input_meta
        }
        output_meta = session.get_outputs()

        config = _preprocess_config(self.spec, input_shape, input_shapes)
        output = _output_config(self.spec)
        classes = output["classes"]

        warnings: list[dict[str, Any]] = [
            _warning(
                "non_diagnostic_model",
                "模型级分类结果，非逐搏诊断，不能替代医生判断",
            ),
            _warning(
                "third_party_model",
                f"模型由第三方模块提供：{self.spec.module_id}",
            ),
        ]
        if len(output_meta) > 1:
            warnings.append(
                _warning(
                    "multiple_outputs",
                    f"模型有 {len(output_meta)} 个输出，仅使用第一个",
                )
            )

        if config["kind"] == "relay":
            return self._analyze_relay(
                session=session,
                input_meta=input_meta,
                config=config,
                output=output,
                classes=classes,
                warnings=warnings,
                record_id=record_id,
                analysis_id=analysis_id,
                samples=samples,
                fs=float(fs),
                lead=lead,
                tail_mode=tail_mode,
                started=started,
                started_perf=started_perf,
            )
        return self._analyze_windows(
            session=session,
            input_meta=input_meta,
            config=config,
            output=output,
            classes=classes,
            warnings=warnings,
            record_id=record_id,
            analysis_id=analysis_id,
            samples=samples,
            fs=float(fs),
            lead=lead,
            tail_mode=tail_mode,
            started=started,
            started_perf=started_perf,
        )

    # ------------------------------------------------------------------ 窗口
    def _analyze_windows(
        self,
        *,
        session: Any,
        input_meta: list[Any],
        config: dict[str, Any],
        output: dict[str, Any],
        classes: list[str],
        warnings: list[dict[str, Any]],
        record_id: str,
        analysis_id: str,
        samples: np.ndarray,
        fs: float,
        lead: str,
        tail_mode: str,
        started: datetime,
        started_perf: float,
    ) -> dict[str, Any]:
        input_name = str(getattr(input_meta[0], "name", "x"))
        input_shape = _declared_shape(getattr(input_meta[0], "shape", []) or [])

        target_fs = float(config["samplingRate"] or fs)
        signal, resampled = _resample(
            np.asarray(samples, dtype=np.float32), float(fs), target_fs
        )
        if resampled:
            warnings.append(
                _warning(
                    "resampled",
                    f"采样率 {float(fs):g} Hz 已重采样到 {target_fs:g} Hz",
                )
            )
        expected_lead = config["lead"]
        if expected_lead and lead and expected_lead.upper() != str(lead).upper():
            warnings.append(
                _warning(
                    "lead_mismatch",
                    f"模型期望导联 {expected_lead}，当前记录导联为 {lead}",
                )
            )

        windows, padded = _build_windows(
            signal,
            config["windowSamples"],
            config["strideSamples"],
            tail_mode,
        )
        if padded:
            warnings.append(
                _warning(
                    "tail_padded",
                    f"末尾不足一个窗口，已零填充 {padded} 个采样点",
                )
            )
        normalized = _normalize(windows, config["normalize"])
        data = _fit_input(
            normalized,
            input_shape,
            config["channels"],
            config["windowSamples"],
        )
        batch = (
            input_shape[0]
            if input_shape and isinstance(input_shape[0], int) and input_shape[0] > 0
            else None
        )

        raw = _run(session, input_name, data, batch)
        probabilities = _probabilities(raw, classes)
        final = _aggregate(probabilities, output["aggregation"])

        completed_at = datetime.now(UTC)
        duration_ms = round((time.perf_counter() - started_perf) * 1000)
        return _build_result(
            spec=self.spec,
            record_id=record_id,
            analysis_id=analysis_id,
            classes=classes,
            final=final,
            warnings=warnings,
            aggregation=output["aggregation"],
            duration_ms=duration_ms,
            started=started,
            completed_at=completed_at,
            parameters={
                "tailMode": tail_mode,
                "windows": len(windows),
            },
            provenance={
                "preprocess": {
                    key: config[key]
                    for key in (
                        "lead",
                        "samplingRate",
                        "windowSamples",
                        "strideSamples",
                        "normalize",
                        "channels",
                    )
                },
                "inputShape": input_shape,
                "windows": len(windows),
                "aggregation": output["aggregation"],
                "tailMode": tail_mode,
                "resampled": resampled,
            },
            scored=len(windows),
            window_seconds=signal.size / target_fs if target_fs else 0.0,
        )

    # ------------------------------------------------------------------ 逐搏
    def _analyze_relay(
        self,
        *,
        session: Any,
        input_meta: list[Any],
        config: dict[str, Any],
        output: dict[str, Any],
        classes: list[str],
        warnings: list[dict[str, Any]],
        record_id: str,
        analysis_id: str,
        samples: np.ndarray,
        fs: float,
        lead: str,
        tail_mode: str,
        started: datetime,
        started_perf: float,
    ) -> dict[str, Any]:
        x_name, dt_name = _resolve_tensor_names(input_meta, bool(config["hasDt"]))
        x_shape = _input_shape_for(input_meta, x_name) or config["xShape"]

        target_fs = float(config["fs"])
        signal, resampled = _resample(
            np.asarray(samples, dtype=np.float32), fs, target_fs
        )
        if resampled:
            warnings.append(
                _warning(
                    "resampled",
                    f"采样率 {fs:g} Hz 已重采样到 {target_fs:g} Hz",
                )
            )

        channels = _prepare_channels(signal, int(config["leads"]))
        if int(config["leads"]) > 1 and np.asarray(samples).ndim == 1:
            warnings.append(
                _warning(
                    "single_lead_duplicated",
                    f"记录为单导联，已复制为 {config['leads']} 个导联以匹配模型输入",
                    severity="info",
                )
            )
        rpeaks = _detect_rpeaks(channels[:, 0], target_fs)
        beats, positions = _extract_beats(
            channels,
            rpeaks,
            int(config["windowBefore"]),
            int(config["windowAfter"]),
        )
        if config["zscore"]:
            beats = _zscore_beats(beats)

        probabilities_list: list[np.ndarray] = []
        sequences = 0
        dropped = 0
        if config["mode"] == "sequence":
            chunks = _sequence_chunks(
                beats,
                positions,
                int(config["beatsPerWindow"]),
                target_fs,
                float(config["dtMedianSeconds"]),
            )
            sequences = len(chunks)
            scored = sequences * int(config["beatsPerWindow"])
            dropped = int(beats.shape[0]) - scored
            if dropped > 0:
                warnings.append(
                    _warning(
                        "tail_beats_dropped",
                        f"末尾 {dropped} 个心搏不足一个 {config['beatsPerWindow']} 搏序列，已丢弃",
                        severity="info",
                    )
                )
            for x, dt in chunks:
                feed = {x_name: np.asarray(x, dtype=np.float32)[None, ...]}
                if dt_name:
                    feed[dt_name] = np.asarray(dt, dtype=np.float32)[None, ...]
                probabilities_list.append(
                    _probabilities(_run_feed(session, feed), classes)
                )
        else:
            scored = int(beats.shape[0])
            batch = _static_batch(x_shape, _MAX_BEAT_BATCH)
            for start in range(0, scored, batch):
                chunk = beats[start : start + batch]
                keep = len(chunk)
                if keep < batch:
                    padded = np.zeros((batch, *chunk.shape[1:]), dtype=np.float32)
                    padded[:keep] = chunk
                    chunk = padded
                raw = _run_feed(
                    session, {x_name: np.asarray(chunk, dtype=np.float32)}
                )
                probabilities_list.append(_probabilities(raw, classes)[:keep])

        probabilities = np.concatenate(probabilities_list, axis=0)
        final = _aggregate(probabilities, output["aggregation"])

        # 逐搏类别 → 心率 / HRV / 异常占比。序列模型只统计完整序列，
        # 被丢弃的尾部心搏不参与比例与 RR 统计，与 beatsDropped 保持一致。
        scored_positions = positions[:scored]
        labels = probabilities.argmax(axis=1)
        class_counts = {
            name: int(np.sum(labels == index))
            for index, name in enumerate(classes)
        }
        n_used = int(labels.size)
        mean_confidence = (
            float(probabilities.max(axis=1).mean()) if n_used else 0.0
        )
        rr_ms = (
            np.diff(scored_positions) / target_fs * 1000.0
            if n_used > 1
            else np.asarray([], dtype=np.float64)
        )
        heart_rate = (
            float(60000.0 / float(np.mean(rr_ms))) if rr_ms.size else None
        )

        quality: Any = None
        quality_dict: dict[str, Any] | None = None
        try:
            quality = assess_quality(
                EcgSignal(
                    samples=np.ascontiguousarray(channels[:, 0], dtype=np.float32),
                    fs=target_fs,
                    lead=str(lead or "unknown"),
                    source="record",
                ),
                rpeaks,
            )
            quality_dict = quality.to_dict()
            warnings.extend(quality.warnings)
        except Exception as exc:  # noqa: BLE001 - 质量评估失败不应让分析失败
            warnings.append(
                _warning(
                    "quality_unavailable",
                    f"信号质量评估失败：{type(exc).__name__}",
                    severity="info",
                )
            )

        extra_measurements = compute_measurements(
            r_positions=scored_positions,
            fs=target_fs,
            class_counts=class_counts,
            n_beats=n_used,
            duration_sec=float(channels.shape[0]) / target_fs,
            quality_score=quality.score if quality is not None else 0.0,
            record_id=record_id,
            analysis_id=analysis_id,
            id_factory=new_id,
        )
        ratio_codes = {"n_ratio", "svb_ratio", "veb_ratio", "f_ratio"}
        for item in extra_measurements:
            if item.get("code") in ratio_codes:
                item["method"] = f"{self.spec.module_id}:{self.spec.model_id}"

        completed_at = datetime.now(UTC)
        duration_ms = round((time.perf_counter() - started_perf) * 1000)
        return _build_result(
            spec=self.spec,
            record_id=record_id,
            analysis_id=analysis_id,
            classes=classes,
            final=final,
            warnings=warnings,
            aggregation=output["aggregation"],
            duration_ms=duration_ms,
            started=started,
            completed_at=completed_at,
            quality=quality_dict,
            extra_measurements=extra_measurements,
            summary=_relay_summary(heart_rate, class_counts, n_used),
            parameters={
                "tailMode": tail_mode,
                "mode": config["mode"],
                "leads": int(config["leads"]),
                "windowSamples": int(config["windowSamples"]),
                "beatsPerWindow": int(config["beatsPerWindow"]),
                "sequenceLength": int(config["beatsPerWindow"]),
                "beatsScored": scored,
                "beatsDropped": dropped,
                "sequences": sequences,
                "nBeatsDetected": int(beats.shape[0]),
                "nBeatsClassified": n_used,
                "classCounts": class_counts,
                "meanConfidence": round(mean_confidence, 4),
                "heartRate": round(heart_rate, 1) if heart_rate is not None else None,
                "qualityMetrics": quality.metrics if quality is not None else None,
                "lead": str(lead or "unknown"),
                "originalFs": fs,
                "resampled": resampled,
            },
            provenance={
                "preprocess": {
                    "pipeline": config["pipeline"],
                    "samplingRate": target_fs,
                    "windowSamples": int(config["windowSamples"]),
                    "windowBefore": int(config["windowBefore"]),
                    "windowAfter": int(config["windowAfter"]),
                    "beatsPerWindow": int(config["beatsPerWindow"]),
                    "leads": int(config["leads"]),
                    "normalize": "zscore-per-lead" if config["zscore"] else "none",
                    "dtMedianSeconds": float(config["dtMedianSeconds"]),
                },
                "inputShape": x_shape,
                "inputNames": [name for name in (x_name, dt_name) if name],
                "rpeaks": int(rpeaks.size),
                "beats": int(beats.shape[0]),
                "beatsScored": scored,
                "beatsDropped": dropped,
                "sequences": sequences,
                "aggregation": output["aggregation"],
                "tailMode": tail_mode,
                "resampled": resampled,
                "qualityAssessed": quality is not None,
            },
            scored=scored,
            window_seconds=signal.size / target_fs if target_fs else 0.0,
        )


__all__ = ["OnnxEngineError", "OnnxEngineRunner"]

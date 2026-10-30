"""通用 ONNX 分析引擎执行器（A3）。

加载 ``analysis-model`` 模块自带、经过 sha256 校验的单个 ONNX 文件，按
manifest 的受控 ``preprocess`` / ``output`` 字段做推理，并映射成合法的
``AnalysisResult``。

受控范围（其余字段只记录、不执行）：

- ``preprocess``：``lead``、``samplingRate``（或 ``fs``）、``windowSamples``、
  ``strideSamples``、``normalize``（``none|zscore|minmax``）、``channels``；
- ``output``：``{"type": "classification", "classes": [...],
  "aggregation": "mean|max"}``。

任何形状/类型不匹配都抛 ``OnnxEngineError``（落库为 ``engine_error``），
不静默返回空结果。模型级分类不是逐搏诊断，结果里固定带非诊断警告。

限制：只支持单输入、单输出的单文件 ONNX；外部权重文件（external data）、
多输入特征模型不在本版范围。
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
from ..analysis.types import SCHEMA_ANALYSIS, SCHEMA_MEASUREMENT, EcgSignal
from .engines import ModuleModelSpec

logger = logging.getLogger(__name__)

_ENGINE_VERSION = "1.0.0"
_ALLOWED_NORMALIZE = {"none", "zscore", "minmax"}
_ALLOWED_AGGREGATION = {"mean", "max"}

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


def _preprocess_config(
    spec: ModuleModelSpec, input_shape: list[Any]
) -> dict[str, Any]:
    pre = spec.model.get("preprocess")
    inputs = spec.model.get("input")
    pre = pre if isinstance(pre, dict) else {}
    inputs = inputs if isinstance(inputs, dict) else {}

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

    return {
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


# ---------------------------------------------------------------------- 预处理
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
    if rank == 2:
        last = shape[1]
        if _dim_ok(last, window):
            return windows
        if channels > 1:
            return windows.reshape(count, window * channels)
        raise OnnxEngineError(f"模型输入特征维 {last} 与窗口长度 {window} 不匹配")
    if rank == 3:
        first, second = shape[1], shape[2]
        if _dim_ok(first, channels) and _dim_ok(second, window):
            return windows.reshape(count, channels, window)
        if _dim_ok(first, window) and _dim_ok(second, channels):
            return windows.reshape(count, window, channels)
        raise OnnxEngineError(
            f"模型输入形状 {shape} 与通道/窗口 {channels}/{window} 不匹配"
        )
    raise OnnxEngineError(f"仅支持 2/3 维输入，模型输入维度为 {rank}")


# ---------------------------------------------------------------------- 推理
def _run(session: Any, input_name: str, data: np.ndarray, batch: int | None) -> Any:
    def _call(chunk: np.ndarray) -> Any:
        try:
            return session.run(None, {input_name: chunk.astype(np.float32)})[0]
        except Exception as exc:
            raise OnnxEngineError(f"ONNX 推理失败：{exc}"[:300]) from exc

    if batch is None:
        return _call(data)
    chunks: list[np.ndarray] = []
    for start in range(0, len(data), batch):
        chunk = data[start : start + batch]
        keep = len(chunk)
        if keep < batch:
            # 静态 batch 的模型（如 onnxruntime 自带 mul_1）要求固定批大小。
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
    try:
        values = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise OnnxEngineError("模型输出不是数值张量") from exc
    count = len(classes)
    if values.ndim == 1:
        if values.size != count:
            raise OnnxEngineError(
                f"模型输出形状 {values.shape} 与类别数 {count} 不匹配"
            )
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != count:
        raise OnnxEngineError(
            f"模型输出形状 {values.shape} 与类别数 {count} 不匹配"
        )
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
        input_meta = session.get_inputs()[0]
        input_shape = list(getattr(input_meta, "shape", []) or [])
        output_meta = session.get_outputs()

        preprocess = _preprocess_config(self.spec, input_shape)
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

        target_fs = float(preprocess["samplingRate"] or fs)
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
        expected_lead = preprocess["lead"]
        if expected_lead and lead and expected_lead.upper() != str(lead).upper():
            warnings.append(
                _warning(
                    "lead_mismatch",
                    f"模型期望导联 {expected_lead}，当前记录导联为 {lead}",
                )
            )

        windows, padded = _build_windows(
            signal,
            preprocess["windowSamples"],
            preprocess["strideSamples"],
            tail_mode,
        )
        if padded:
            warnings.append(
                _warning(
                    "tail_padded",
                    f"末尾不足一个窗口，已零填充 {padded} 个采样点",
                )
            )
        normalized = _normalize(windows, preprocess["normalize"])
        data = _fit_input(
            normalized,
            input_shape,
            preprocess["channels"],
            preprocess["windowSamples"],
        )
        batch = (
            input_shape[0]
            if input_shape and isinstance(input_shape[0], int) and input_shape[0] > 0
            else None
        )
        if len(output_meta) > 1:
            warnings.append(
                _warning(
                    "multiple_outputs",
                    f"模型有 {len(output_meta)} 个输出，仅使用第一个",
                )
            )

        raw = _run(session, input_meta.name, data, batch)
        probabilities = _probabilities(raw, classes)
        final = _aggregate(probabilities, output["aggregation"])

        completed_at = datetime.now(UTC)
        duration_ms = round((time.perf_counter() - started_perf) * 1000)
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
                "code": f"{self.spec.module_id}.class_probability.{_slug(name)}",
                "label": f"{name} 概率",
                "value": round(float(value) * 100.0, 4),
                "unit": "%",
                "ucum": "",
                "range": {
                    "startSec": 0,
                    "endSec": round(float(signal.size) / target_fs, 3),
                },
                "method": self.spec.model_id,
                "warnings": [],
            }
            for name, value in zip(classes, final, strict=True)
        ]

        return {
            "schema": SCHEMA_ANALYSIS,
            "id": analysis_id,
            "recordId": record_id,
            "engine": self.spec.engine_id,
            "moduleId": self.spec.module_id,
            "modelId": self.spec.model_id,
            "modelVersion": self.spec.module_version,
            "task": str(self.spec.model.get("task") or "beat-classification"),
            "status": "completed",
            "startedAt": rfc3339(started),
            "completedAt": rfc3339(completed_at),
            "durationMs": duration_ms,
            "summary": summary,
            "quality": None,
            "measurements": measurements,
            "beats": [],
            "beatsRef": None,
            "annotations": [],
            "warnings": warnings,
            "parameters": {
                "engine": self.spec.engine_id,
                "engineVersion": _ENGINE_VERSION,
                "modelFormat": "onnx",
                "classOrder": classes,
                "aggregation": output["aggregation"],
                "windows": len(windows),
                "tailMode": tail_mode,
            },
            "provenance": {
                "engine": f"eclipse-health-backend/analysis_service/onnx@{_ENGINE_VERSION}",
                "modelSource": f"module:{self.spec.module_id}",
                "moduleVersion": self.spec.module_version,
                "modelFile": self.spec.model_relative_path,
                "modelSha256": self.spec.model_sha256,
                "preprocess": {
                    key: preprocess[key]
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
        }


__all__ = ["OnnxEngineError", "OnnxEngineRunner"]

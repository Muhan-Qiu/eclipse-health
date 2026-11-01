"""Relay ECG 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``list_models`` / ``analyze`` /
``stats`` / ``deactivate``。

模型输入严格复刻 V1 ``train_mitbih.py``：360 Hz、两导联、R 峰前后 90/144 采样点
（234 点窗口），逐导联 z-score；序列模型每条 64 连搏，Δt = RR / DS1 训练中位数。
权重是 V1 的 PyTorch checkpoint 导出的 ONNX（opset 17，动态 batch），不随 git 提交。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from adapter import (
    AAMI,
    CLASSES,
    DT_MEDIAN_SECONDS,
    NON_DIAGNOSTIC,
    SEQ_LEN,
    WIN_AFTER,
    WIN_BEFORE,
    WINDOW_SAMPLES,
    AdapterError,
    aggregate,
    assert_ours_above_baselines,
    chunk_sequences,
    extract_beats,
    softmax,
    validate_model_index,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "org.eclipsehealth.relay-ecg")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
MODELS_DIR_ENV = "EH_RELAY_MODELS_DIR"
INDEX_PATH_ENV = "EH_RELAY_INDEX_PATH"
MAX_SIGNAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_WFDB_SECONDS = 3600.0
DEFAULT_MAX_SECONDS = 600.0
MAX_BEAT_DETAILS = 256
MAX_HISTORY = 20

_index_lock = threading.Lock()
_index_cache: dict[str, Any] | None = None
_session_lock = threading.Lock()
_sessions: dict[str, Any] = {}
_warm_state: dict[str, Any] = {"warm": False, "seconds": None, "error": None}
_history: list[dict[str, Any]] = []


def _module_dir() -> Path:
    injected = os.environ.get("ECLIPSE_MODULE_DIR")
    return Path(injected) if injected else Path(__file__).resolve().parents[1]


def _models_dir() -> Path:
    override = os.environ.get(MODELS_DIR_ENV)
    return Path(override) if override else _module_dir() / "models"


def _index_path() -> Path:
    override = os.environ.get(INDEX_PATH_ENV)
    return Path(override) if override else _module_dir() / "models" / "index.json"


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, error: RpcError) -> None:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data:
        payload["error"]["data"] = error.data
    _write(payload)


# ---------------------------------------------------------------------- 索引
def _load_index() -> dict[str, Any]:
    global _index_cache
    with _index_lock:
        if _index_cache is not None:
            return _index_cache
        path = _index_path()
        if not path.is_file():
            raise AdapterError("index_missing", "models/index.json 不存在", 500)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError("index_invalid", "models/index.json 不是合法 JSON", 500) from exc
        models = validate_model_index(raw)
        assert_ours_above_baselines(models)
        for entry in models:
            if list(entry.get("classes") or []) != CLASSES:
                raise AdapterError("index_invalid", f"模型 {entry['id']} 的 classes 与 V1 不一致", 500)
        index = dict(raw)
        index["models"] = models
        _index_cache = index
        return index


def _find_model(model_id: str) -> dict[str, Any]:
    for entry in _load_index()["models"]:
        if entry["id"] == model_id:
            return entry
    raise AdapterError("model_not_found", f"未知模型：{model_id[:64]}", 404)


def _model_path(entry: dict[str, Any]) -> Path:
    return _models_dir() / str(entry["file"])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session(entry: dict[str, Any]) -> Any:
    path = _model_path(entry)
    if not path.is_file():
        raise AdapterError(
            "model_missing",
            f"{entry['file']} 未安装；请把 V1 导出的 ONNX 放到模块 models/ 目录",
            503,
        )
    expected = str(entry.get("sha256") or "")
    if expected and _sha256(path) != expected:
        raise AdapterError("model_sha_mismatch", f"{entry['file']} 校验失败", 500)
    with _session_lock:
        if entry["id"] in _sessions:
            return _sessions[entry["id"]]
        try:
            import onnxruntime as ort

            options = ort.SessionOptions()
            if str((entry.get("input") or {}).get("mode") or "sequence") == "sequence":
                # 模型文件保持 dynamic batch；会话创建时把 batch 固定为 1，
                # 否则 ORT 要对上万节点做符号形状推导，k12 加载会超过十分钟。
                options.add_free_dimension_override_by_name("batch", 1)
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise AdapterError(
                "model_load_failed", f"{entry['file']} 加载失败：{type(exc).__name__}", 500
            ) from exc
        _sessions[entry["id"]] = session
        return session


# ---------------------------------------------------------------------- 输入
def _positive_float(value: Any, default: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number <= 0 or number > upper:
        return default
    return number


def _slice_signal(
    signal: Any, fs: float, options: dict[str, Any], default_seconds: float | None
) -> tuple[Any, int]:
    import numpy as np

    array = np.asarray(signal, dtype=np.float32)
    start_seconds = max(0.0, float(options.get("startSeconds") or 0.0))
    raw_max = options.get("maxSeconds", default_seconds)
    if raw_max is None:
        start = min(round(start_seconds * fs), array.shape[0])
        return array[start:], start
    seconds = _positive_float(raw_max, default_seconds or MAX_WFDB_SECONDS, MAX_WFDB_SECONDS)
    start = min(round(start_seconds * fs), array.shape[0])
    stop = min(array.shape[0], start + round(seconds * fs))
    return array[start:stop], start


def _resolve_leads(
    requested: Any, sig_names: list[str], n_channels: int
) -> tuple[list[int] | None, list[str]]:
    if requested is None:
        chosen = list(range(min(2, n_channels)))
        return chosen, [sig_names[index] if index < len(sig_names) else f"ch{index}" for index in chosen]
    names = [requested] if isinstance(requested, str) else list(requested)
    indices: list[int] = []
    resolved: list[str] = []
    for item in names:
        if isinstance(item, int) and not isinstance(item, bool):
            if item < 0 or item >= n_channels:
                raise AdapterError("invalid_lead", f"导联下标 {item} 超出范围", 400)
            indices.append(item)
            resolved.append(sig_names[item] if item < len(sig_names) else f"ch{item}")
            continue
        if not isinstance(item, str):
            raise AdapterError("invalid_lead", "leads 必须是导联名或下标", 400)
        lowered = [name.lower() for name in sig_names]
        if item.lower() not in lowered:
            raise AdapterError("invalid_lead", f"记录里没有导联 {item[:32]}", 400)
        index = lowered.index(item.lower())
        indices.append(index)
        resolved.append(sig_names[index])
    return indices, resolved


def _detect_rpeaks(signal: Any, fs: float) -> list[int]:
    import numpy as np

    first = np.asarray(signal, dtype=np.float32)
    if first.ndim == 2:
        first = first[:, 0]
    try:
        from wfdb.processing import xqrs_detect

        peaks = xqrs_detect(sig=first, fs=fs, verbose=False)
    except Exception as exc:
        raise AdapterError("beat_detection_failed", f"R 峰检测失败：{type(exc).__name__}", 422) from exc
    return [int(value) for value in peaks]


def _read_wfdb(params: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    try:
        import wfdb
    except ImportError as exc:
        raise AdapterError("dependency_missing", "模块环境缺少 wfdb", 503) from exc

    raw = str(params.get("wfdbPath") or "")
    if not raw:
        raise AdapterError("invalid_input", "params.wfdbPath 缺失", 400)
    base = Path(raw)
    if base.suffix.lower() in {".hea", ".dat", ".atr"}:
        base = base.with_suffix("")
    if not (base.parent / f"{base.name}.hea").is_file():
        raise AdapterError("invalid_input", "WFDB .hea 文件不存在", 400)

    try:
        record = wfdb.rdrecord(str(base))
    except Exception as exc:
        raise AdapterError("invalid_input", f"WFDB 读取失败：{type(exc).__name__}", 400) from exc
    if record.p_signal is None:
        raise AdapterError("invalid_signal", "WFDB 记录没有物理信号", 422)
    fs = float(record.fs)
    signal = np.asarray(record.p_signal, dtype=np.float32)
    sig_names = [str(name) for name in (record.sig_name or [])]
    lead_indices, lead_names = _resolve_leads(params.get("leads"), sig_names, signal.shape[1])
    signal, offset = _slice_signal(signal, fs, options, DEFAULT_MAX_SECONDS)

    annotated = False
    positions: list[int] = []
    try:
        ann = wfdb.rdann(str(base), "atr")
    except Exception:  # noqa: BLE001 - 没有 atr 时退回检测
        ann = None
    if ann is not None:
        stop = offset + signal.shape[0]
        for sample, symbol in zip(ann.sample, ann.symbol, strict=False):
            peak = int(sample)
            if AAMI.get(symbol) is not None and offset <= peak < stop:
                positions.append(peak - offset)
        annotated = bool(positions)
    if not positions:
        positions = _detect_rpeaks(signal, fs)
    return {
        "signal": signal,
        "fs": fs,
        "rpeaks": positions,
        "leadIndices": lead_indices,
        "leadNames": lead_names,
        "source": "wfdb",
        "annotated": annotated,
        "offset": offset,
    }


def _read_signal_ref(params: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    ref = params.get("signalRef")
    if not isinstance(ref, dict):
        raise AdapterError("invalid_input", "params.signalRef 缺失", 400)
    path = Path(str(ref.get("path") or ""))
    if not path.is_file():
        raise AdapterError("invalid_input", "signalRef.path 不是可读文件", 400)
    if path.stat().st_size > MAX_SIGNAL_BYTES:
        raise AdapterError("invalid_input", "波形文件超过 2GB 上限", 400)
    blob = path.read_bytes()
    expected = str(ref.get("sha256") or "")
    if expected and hashlib.sha256(blob).hexdigest() != expected:
        raise AdapterError("invalid_input", "波形文件校验失败", 400)
    if len(blob) % 4 != 0:
        raise AdapterError("invalid_input", "波形文件不是 float32 数组", 400)
    samples = np.frombuffer(blob, dtype="<f4").astype(np.float32)
    channels = int(ref.get("channels") or 1)
    if channels > 1:
        if samples.size % channels != 0:
            raise AdapterError("invalid_input", "样本数与 channels 不整除", 400)
        samples = samples.reshape(-1, channels)
    fs = float(ref.get("fs") or 0)
    signal, _ = _slice_signal(samples, fs, options, None)
    positions = params.get("rpeaks")
    if positions is None:
        positions = _detect_rpeaks(signal, fs)
    elif not isinstance(positions, list):
        raise AdapterError("invalid_input", "rpeaks 必须是采样下标数组", 400)
    lead = str(ref.get("lead") or "unknown")
    return {
        "signal": signal,
        "fs": fs,
        "rpeaks": [int(value) for value in positions],
        "leadIndices": None,
        "leadNames": [lead, lead],
        "source": "signalRef",
        "annotated": bool(params.get("rpeaks") is not None),
        "offset": 0,
    }


def _read_samples(params: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    raw = params.get("samples")
    if raw is None:
        raise AdapterError("invalid_input", "需要 params.wfdbPath、params.signalRef 或 params.samples", 400)
    try:
        samples = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise AdapterError("invalid_input", "samples 不是数值数组", 400) from exc
    if samples.ndim == 2 and samples.shape[0] <= 4 and samples.shape[1] > samples.shape[0]:
        samples = samples.T
    fs = float(params.get("fs") or 0)
    signal, _ = _slice_signal(samples, fs, options, None)
    positions = params.get("rpeaks")
    if positions is None:
        positions = _detect_rpeaks(signal, fs)
    elif not isinstance(positions, list):
        raise AdapterError("invalid_input", "rpeaks 必须是采样下标数组", 400)
    return {
        "signal": signal,
        "fs": fs,
        "rpeaks": [int(value) for value in positions],
        "leadIndices": None,
        "leadNames": ["ch0", "ch1"],
        "source": "samples",
        "annotated": bool(params.get("rpeaks") is not None),
        "offset": 0,
    }


def _load_signal(params: dict[str, Any]) -> dict[str, Any]:
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    if params.get("wfdbPath") is not None:
        return _read_wfdb(params, options)
    if params.get("signalRef") is not None:
        return _read_signal_ref(params, options)
    return _read_samples(params, options)


# ---------------------------------------------------------------------- 推理
def _run_sequence(session: Any, entry: dict[str, Any], x: Any, dt: Any) -> Any:
    import numpy as np

    tensors = (entry.get("input") or {}).get("tensors") or {}
    feed: dict[str, Any] = {"x": np.asarray(x, dtype=np.float32)[None, ...]}
    if "dt" in tensors:
        feed["dt"] = np.asarray(dt, dtype=np.float32)[None, ...]
    return session.run(None, feed)[0]


def _run_beat(session: Any, x: Any) -> Any:
    import numpy as np

    return session.run(None, {"x": np.asarray(x, dtype=np.float32)})[0]


def _analyze(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    model_id = params.get("modelId")
    if not isinstance(model_id, str) or not model_id:
        model_id = _load_index()["models"][0]["id"]
    entry = _find_model(model_id)
    session = _session(entry)

    loaded = _load_signal(params)
    fs = float(loaded["fs"])
    beats, positions = extract_beats(
        loaded["signal"], loaded["rpeaks"], fs, loaded["leadIndices"]
    )
    mode = str((entry.get("input") or {}).get("mode") or "sequence")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    probabilities: list[np.ndarray] = []
    chunks: list[dict[str, Any]] = []
    if mode == "beat":
        for start in range(0, beats.shape[0], 256):
            logits = _run_beat(session, beats[start:start + 256])
            probabilities.append(softmax(logits))
        scored = int(beats.shape[0])
        dropped = 0
    else:
        sequences = chunk_sequences(beats, positions, SEQ_LEN)
        for start, x, dt in sequences:
            logits = _run_sequence(session, entry, x, dt)
            probs = softmax(logits[0])
            probabilities.append(probs)
            chunk_summary = aggregate(probs, CLASSES)
            chunks.append(
                {
                    "startBeat": int(start),
                    "predictedClass": chunk_summary["predictedClass"],
                    "probabilities": chunk_summary["probabilities"],
                }
            )
        scored = len(sequences) * SEQ_LEN
        dropped = int(beats.shape[0]) - scored

    probs = np.concatenate(probabilities, axis=0)
    summary = aggregate(probs, CLASSES)
    result: dict[str, Any] = {
        "engine": "relay-v1",
        "modelId": entry["id"],
        "modelName": entry["name"],
        "modelClass": entry["class"],
        "score": entry["score"],
        "metric": entry["metric"],
        "source": loaded["source"],
        "fs": fs,
        "leads": loaded["leadNames"],
        "annotated": bool(loaded["annotated"]),
        "window": {"before": WIN_BEFORE, "after": WIN_AFTER, "samples": WINDOW_SAMPLES},
        "dtMedianSeconds": round(DT_MEDIAN_SECONDS, 6),
        "nBeats": int(beats.shape[0]),
        "nScoredBeats": scored,
        "droppedTailBeats": dropped,
        "sequences": chunks,
        "summary": summary,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    if bool(options.get("includeBeats", False)):
        predicted = probs.argmax(axis=1)
        details = [
            {
                "sample": int(positions[index]),
                "predicted": CLASSES[int(predicted[index])],
                "probabilities": [round(float(value), 4) for value in probs[index]],
            }
            for index in range(min(len(predicted), MAX_BEAT_DETAILS))
        ]
        result["beats"] = details
        result["beatsTruncated"] = len(predicted) > len(details)
    return result


def _record_history(result: dict[str, Any]) -> None:
    summary = result["summary"]
    record = {
        "modelId": result["modelId"],
        "modelName": result["modelName"],
        "predictedClass": summary["predictedClass"],
        "confidence": summary["confidence"],
        "nBeats": result["nBeats"],
        "classDistribution": summary["counts"],
        "summaryText": (
            f"{result['modelName']}：{summary['predictedClass']}"
            f"（平均置信度 {summary['confidence']:.1%}），{result['nScoredBeats']} 个心搏"
        ),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    _history.append(record)
    del _history[:-MAX_HISTORY]


def _stats() -> dict[str, Any]:
    latest = _history[-1] if _history else {
        "summaryText": "暂无分析",
        "nBeats": 0,
        "predictedClass": None,
        "confidence": 0.0,
        "classDistribution": {},
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    return {
        "latest": latest,
        "series": [
            {
                "modelId": item["modelId"],
                "predictedClass": item["predictedClass"],
                "confidence": item["confidence"],
                "nBeats": item["nBeats"],
            }
            for item in _history[-8:]
        ],
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


# ---------------------------------------------------------------------- 状态
def _model_status() -> list[dict[str, Any]]:
    models = _load_index()["models"]
    status: list[dict[str, Any]] = []
    for entry in models:
        path = _model_path(entry)
        status.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "class": entry["class"],
                "score": entry["score"],
                "metric": entry["metric"],
                "classes": entry["classes"],
                "input": entry.get("input") or {},
                "parameters": entry.get("parameters"),
                "available": path.is_file(),
            }
        )
    return status


def _health() -> dict[str, Any]:
    try:
        models = _model_status()
        index_error = None
    except AdapterError as exc:
        models = []
        index_error = exc.message
    version = None
    try:
        import onnxruntime as ort

        version = ort.__version__
    except ImportError:
        pass
    available = sum(1 for item in models if item["available"])
    return {
        "ok": True,
        "ready": bool(_warm_state["warm"]),
        "warmupSeconds": _warm_state["seconds"],
        "warmupError": _warm_state["error"],
        "indexError": index_error,
        "models": len(models),
        "modelsAvailable": available,
        "ours": sum(1 for item in models if item["class"] == "ours"),
        "baselines": sum(1 for item in models if item["class"] == "baseline"),
        "weightsDir": "override" if os.environ.get(MODELS_DIR_ENV) else "module",
        "onnxruntime": version,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def _warmup() -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[str] = []
    loaded = 0
    try:
        for entry in _load_index()["models"]:
            if not _model_path(entry).is_file():
                continue
            try:
                _session(entry)
                loaded += 1
            except AdapterError as exc:
                errors.append(f"{entry['id']}: {exc.code}")
    except AdapterError as exc:
        errors.append(exc.code)
    if loaded == 0 and not errors:
        errors.append("no_weights")
    _warm_state["warm"] = not errors
    _warm_state["error"] = "; ".join(errors)[:300] or None
    _warm_state["seconds"] = round(time.perf_counter() - started, 3)
    return _health()


# ---------------------------------------------------------------------- 分发
def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(
                -32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"}
            )
        return {
            "name": "Relay ECG · V1 精选模型包",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "list_models",
                "analyze",
                "stats",
                "deactivate",
            ],
            "health": _health(),
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return _warmup()
    if method == "health":
        return _health()
    if method == "list_models":
        models = _model_status()
        index = _load_index()
        ours = [float(item["score"]) for item in models if item["class"] == "ours"]
        baselines = [float(item["score"]) for item in models if item["class"] == "baseline"]
        return {
            "source": index.get("source", "relay-v1"),
            "metric": index.get("metric", "macro_f1"),
            "scoreProtocol": index.get("scoreProtocol"),
            "models": models,
            "ordering": {
                "oursMin": min(ours) if ours else None,
                "baselineMax": max(baselines) if baselines else None,
                "satisfied": bool(ours and baselines and min(ours) > max(baselines)),
            },
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "analyze":
        result = _analyze(params)
        _record_history(result)
        return result
    if method == "stats":
        return _stats()
    if method == "activate":
        return {"ok": True}
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        result = handle(str(method), params)
        _result(request_id, result)
        return method != "deactivate"
    except AdapterError as error:
        code = -32602 if error.status in {400, 422} else -32000
        _error(
            request_id,
            RpcError(
                code,
                error.message,
                {"code": error.code.upper(), "reason": error.code, "status": error.status},
            ),
        )
        return True
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(
            request_id,
            RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}),
        )
        return True


def main() -> int:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _error(None, RpcError(-32700, "parse error"))
            continue
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

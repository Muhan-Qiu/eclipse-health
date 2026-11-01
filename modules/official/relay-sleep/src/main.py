"""Relay 睡眠分期模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``list_models`` / ``predict`` / ``stats`` / ``deactivate``。

- Relay 模型输入 ``features [B,10,272]`` + ``dt [B,10,1]``，输出 ``logits [B,10,5]``；
- Chambon2018 / AttnSleep 是原始 EEG 端到端模型，输入 ``windows [B,3,C,3000]``，输出 ``logits [B,5]``；
- 只做 272 维冻结特征/原始窗推理，不做 EDF 解码；权重缺失时 ``predict`` 返回业务错误而不是让进程崩溃。
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

import numpy as np
from adapter import (
    CLASSES,
    NON_DIAGNOSTIC,
    AdapterError,
    empty_stats,
    round_logits,
    summarize,
    validate_dt,
    validate_features,
    validate_windows,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "org.eclipsehealth.relay-sleep")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
MAX_NPZ_BYTES = 512 * 1024 * 1024

_session_lock = threading.Lock()
_sessions: dict[str, Any] = {}
_warm_lock = threading.Lock()
_warm_thread: threading.Thread | None = None
_warm_state: dict[str, Any] = {
    "state": "idle",
    "loaded": [],
    "missing": [],
    "mismatch": [],
    "error": None,
    "seconds": None,
}
_integrity: dict[str, bool] = {}


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


def _module_dir() -> Path:
    injected = os.environ.get("ECLIPSE_MODULE_DIR")
    return Path(injected) if injected else Path(__file__).resolve().parents[1]


def _models_dir() -> Path:
    return _module_dir() / "models"


def load_index() -> list[dict[str, Any]]:
    path = _models_dir() / "index.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _model_entry(model_id: Any) -> dict[str, Any]:
    if not isinstance(model_id, str) or not model_id:
        raise AdapterError("invalid_input", "params.modelId 缺失")
    for entry in load_index():
        if entry.get("id") == model_id:
            return entry
    raise AdapterError("unknown_model", f"未知模型 {model_id[:64]}")


def _model_path(entry: dict[str, Any]) -> Path:
    root = _models_dir().resolve()
    target = (root / str(entry.get("file") or "")).resolve()
    if root not in target.parents:
        raise AdapterError("invalid_input", "模型文件路径越界")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_session(entry: dict[str, Any]) -> Any:
    model_id = str(entry["id"])
    with _session_lock:
        cached = _sessions.get(model_id)
    if cached is not None:
        return cached
    path = _model_path(entry)
    if not path.is_file():
        raise AdapterError("model_unavailable", f"模型权重未安装：{model_id}")
    expected = str(entry.get("sha256") or "")
    if expected and _integrity.get(model_id) is False:
        raise AdapterError("model_corrupt", f"模型权重 sha256 不匹配：{model_id}")
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise AdapterError("dependency_missing", "模块 venv 中缺少 onnxruntime") from exc
    try:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception as exc:  # ORT 的异常类型不稳定
        raise AdapterError("model_load_failed", f"{type(exc).__name__}: {exc}"[:300]) from exc
    with _session_lock:
        _sessions[model_id] = session
    return session


def _warm_worker() -> None:
    started = time.perf_counter()
    _warm_state["state"] = "warming"
    loaded: list[str] = []
    missing: list[str] = []
    mismatch: list[str] = []
    try:
        for entry in load_index():
            model_id = str(entry.get("id"))
            path = _model_path(entry)
            if not path.is_file():
                missing.append(model_id)
                continue
            expected = str(entry.get("sha256") or "")
            actual = _sha256(path)
            _integrity[model_id] = not expected or actual == expected
            if expected and actual != expected:
                mismatch.append(model_id)
                continue
            try:
                _load_session(entry)
            except AdapterError as error:
                _warm_state["error"] = error.message
                missing.append(model_id)
                continue
            loaded.append(model_id)
        _warm_state["state"] = "ready"
    except Exception as exc:  # noqa: BLE001 - 预热失败必须可查询
        _warm_state["state"] = "failed"
        _warm_state["error"] = f"{type(exc).__name__}: {exc}"[:300]
    _warm_state["loaded"] = loaded
    _warm_state["missing"] = missing
    _warm_state["mismatch"] = mismatch
    _warm_state["seconds"] = round(time.perf_counter() - started, 3)


def start_warmup() -> dict[str, Any]:
    global _warm_thread
    with _warm_lock:
        thread_idle = _warm_thread is None or not _warm_thread.is_alive()
        if thread_idle and _warm_state["state"] != "ready":
            _warm_state["state"] = "warming"
            _warm_state["error"] = None
            _warm_thread = threading.Thread(target=_warm_worker, name="relay-warmup", daemon=True)
            _warm_thread.start()
    return _health()


def _health() -> dict[str, Any]:
    return {
        "ok": _warm_state["state"] != "failed",
        "state": _warm_state["state"],
        "warmupSeconds": _warm_state["seconds"],
        "loaded": list(_warm_state["loaded"]),
        "missing": list(_warm_state["missing"]),
        "mismatch": list(_warm_state["mismatch"]),
        "error": _warm_state["error"],
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def _list_models() -> dict[str, Any]:
    items = []
    for entry in load_index():
        path = _model_path(entry)
        items.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "class": entry.get("class"),
                "score": entry.get("score"),
                "metric": entry.get("metric"),
                "seqLen": entry.get("seqLen"),
                "classes": entry.get("classes") or CLASSES,
                "inputKind": entry.get("inputKind"),
                "inputShape": entry.get("inputShape"),
                "parameters": entry.get("parameters"),
                "available": path.is_file(),
                "sha256Match": _integrity.get(str(entry.get("id"))),
            }
        )
    return {"models": items, "count": len(items), "nonDiagnostic": NON_DIAGNOSTIC}


def _read_npz(path_value: Any, family: str) -> tuple[Any, Any]:
    path = Path(str(path_value or ""))
    if not path.is_file():
        raise AdapterError("invalid_input", "npz 文件不存在")
    if path.suffix.lower() != ".npz":
        raise AdapterError("invalid_input", "只接受 .npz 文件")
    if path.stat().st_size > MAX_NPZ_BYTES:
        raise AdapterError("invalid_input", "npz 文件超过 512MB")
    try:
        with np.load(path, allow_pickle=False) as data:
            keys = set(data.files)
            if family == "relay":
                key = "features" if "features" in keys else "X"
                if key not in keys:
                    raise AdapterError("invalid_input", "npz 缺少 features/X 数组")
                dt = data["dt"] if "dt" in keys else None
                return data[key], dt
            key = "windows" if "windows" in keys else "X"
            if key not in keys:
                raise AdapterError("invalid_input", "npz 缺少 windows/X 数组")
            return data[key], None
    except AdapterError:
        raise
    except Exception as exc:  # 损坏 npz 统一转输入错误
        raise AdapterError("invalid_input", f"npz 读取失败：{type(exc).__name__}") from exc


def _predict(params: dict[str, Any]) -> dict[str, Any]:
    entry = _model_entry(params.get("modelId"))
    family = "baseline" if entry.get("inputKind") == "raw-windows" else "relay"
    source = params.get("npzPath")
    if isinstance(params.get("features"), str):
        source = params["features"]
    if isinstance(params.get("windows"), str):
        source = params["windows"]

    if source is not None:
        values, npz_dt = _read_npz(source, family)
    elif family == "relay":
        values = params.get("features")
        npz_dt = params.get("dt")
    else:
        values = params.get("windows")
        npz_dt = None

    if family == "relay":
        features = validate_features(values)
        dt = validate_dt(npz_dt, features.shape[0])
        inputs = {"features": features, "dt": dt}
        unit = "window"
    else:
        channels = int(entry.get("channels") or (entry.get("inputShape") or [0, 0])[1])
        windows = validate_windows(values, channels)
        inputs = {"windows": windows}
        unit = "sequence"

    session = _load_session(entry)
    try:
        logits = np.asarray(session.run(None, inputs)[0])
    except Exception as exc:  # ORT 运行时异常
        raise AdapterError("inference_failed", f"{type(exc).__name__}: {exc}"[:300]) from exc
    if logits.ndim < 2 or logits.shape[-1] != len(CLASSES):
        raise AdapterError("inference_failed", "模型输出类别维不是 5")

    return {
        "modelId": entry.get("id"),
        "name": entry.get("name"),
        "family": family,
        "class": entry.get("class"),
        "seqLen": entry.get("seqLen"),
        "classes": entry.get("classes") or CLASSES,
        "shape": list(logits.shape),
        "logits": round_logits(logits),
        "argmax": np.asarray(logits).argmax(axis=-1).tolist(),
        "summary": summarize(logits, unit),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "Relay Sleep · 睡眠分期",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "list_models", "predict", "stats", "deactivate"],
            "health": _health(),
        }
    if method == "warmup":
        return start_warmup()
    if method == "health":
        return _health()
    if method == "list_models":
        return _list_models()
    if method == "predict":
        entry = _model_entry(params.get("modelId"))
        path = _model_path(entry)
        if not path.is_file():
            return {
                "error": {
                    "code": "model_unavailable",
                    "message": f"模型权重未安装：{entry.get('id')}",
                }
            }
        return _predict(params)
    if method == "stats":
        return empty_stats()
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
        _error(request_id, RpcError(-32602, error.message, {"code": "INVALID_INPUT", "reason": error.code}))
        return True
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
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
    raise SystemExit(main())

"""Cardia 2.0 ``analysis-model`` 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``analyze`` / ``deactivate``。

- 波形通过核心提供的临时 float32 文件句柄传入（``signalRef``），并按 sha256 校验；
- 模块自带 onnxsim 简化权重（``models/cardia_k4_best_sim.onnx``），预热时通过
  ``EH_CARDIA_MODEL_PATH`` 指向它；文件缺失时回退核心默认权重（简化图优先，再回退原图）；
- 预热（ONNX 会话初始化）在后台线程执行，``warmup`` 立即返回，``health`` 轮询；
- 分析业务失败（心搏不足/信号非法/模型加载失败）以 ``{"error": {...}}`` 结果返回，
  传输层错误才用 JSON-RPC error；
- 结果 JSON 超过 3.5MB 时写入临时文件并返回 ``resultRef``，避免触碰宿主 4MB 单行上限。
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

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "org.eclipsehealth.cardia")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")

MODEL_FILE = "cardia_k4_best_sim.onnx"
MODEL_PATH_ENV = "EH_CARDIA_MODEL_PATH"

RESULT_INLINE_LIMIT_BYTES = 3_500_000
MAX_SIGNAL_BYTES = 2 * 1024 * 1024 * 1024

_warm_lock = threading.Lock()
_warm_state: dict[str, Any] = {
    "warm": False,
    "error": None,
    "seconds": None,
    "startedAt": None,
    "model": None,
}
_warm_thread: threading.Thread | None = None


def _module_dir() -> Path:
    """安装目录（核心注入）优先，源码目录兜底。"""
    injected = os.environ.get("ECLIPSE_MODULE_DIR")
    return Path(injected) if injected else Path(__file__).resolve().parents[1]


def configure_model() -> Path | None:
    """让分析库优先加载模块自带简化权重；返回权重路径，缺失时返回 None。

    核心启动模块时只继承白名单环境变量，所以 ``EH_CARDIA_MODEL_PATH`` 由模块自己
    设置；用户显式 ``EH_CARDIA_MODEL=original`` 时由分析库优先，仍走原图。
    """
    candidate = _module_dir() / "models" / MODEL_FILE
    if not candidate.is_file():
        return None
    os.environ.setdefault(MODEL_PATH_ENV, str(candidate))
    return candidate


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


# ---------------------------------------------------------------------- 预热
def _warm_worker() -> None:
    started = time.perf_counter()
    _warm_state["startedAt"] = started
    try:
        configure_model()
        import_started = time.perf_counter()
        from eclipse_health_backend.analysis.model import (
            CardiaModel,
            session_init_seconds,
        )

        import_seconds = time.perf_counter() - import_started
        model = CardiaModel()  # 只初始化 ONNX 会话，不推理
        _warm_state["model"] = {
            "file": model.info.model_path.name,
            "sha256": model.info.model_sha256,
            "variant": model.info.model_variant,
            "importSeconds": round(import_seconds, 3),
            "sessionInitSeconds": session_init_seconds(model.info.model_sha256),
        }
        _warm_state["warm"] = True
        _warm_state["seconds"] = round(time.perf_counter() - started, 3)
    except Exception as exc:  # noqa: BLE001 - 预热失败必须可查询
        _warm_state["error"] = f"{type(exc).__name__}: {exc}"[:300]
        _warm_state["seconds"] = round(time.perf_counter() - started, 3)


def start_warmup() -> None:
    global _warm_thread
    with _warm_lock:
        if _warm_state["warm"]:
            return
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        _warm_state["error"] = None
        _warm_state["seconds"] = None
        _warm_state["model"] = None
        _warm_thread = threading.Thread(target=_warm_worker, name="cardia-warmup", daemon=True)
        _warm_thread.start()


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "warm": bool(_warm_state["warm"]),
        "warmupSeconds": _warm_state["seconds"],
        "error": _warm_state["error"],
        "model": _warm_state["model"],
    }


# ---------------------------------------------------------------------- 分析
def _read_signal(ref: dict[str, Any]) -> Any:
    import numpy as np
    from eclipse_health_backend.analysis.types import InvalidSignalError

    path = Path(str(ref.get("path") or ""))
    if not path.is_file():
        raise InvalidSignalError("signalRef.path 不是可读文件")
    size = path.stat().st_size
    if size > MAX_SIGNAL_BYTES:
        raise InvalidSignalError("波形文件超过 2GB 上限")
    blob = path.read_bytes()
    expected = str(ref.get("sha256") or "")
    if expected and hashlib.sha256(blob).hexdigest() != expected:
        raise InvalidSignalError("波形文件校验失败")
    if len(blob) % 4 != 0:
        raise InvalidSignalError("波形文件不是 float32 数组")
    samples = np.frombuffer(blob, dtype="<f4").astype(np.float32)
    n_samples = int(ref.get("nSamples") or 0)
    if n_samples and n_samples != samples.size:
        raise InvalidSignalError("signalRef.nSamples 与实际样本数不一致")
    return samples


def _analyze(params: dict[str, Any]) -> dict[str, Any]:
    from eclipse_health_backend.analysis.engine import analyze
    from eclipse_health_backend.analysis.types import (
        AnalysisOptions,
        EcgSignal,
        InsufficientBeatsError,
        InvalidSignalError,
        ModelLoadError,
    )

    record_id = params.get("recordId")
    if not isinstance(record_id, str) or not record_id:
        raise InvalidSignalError("params.recordId 缺失")
    configure_model()
    analysis_id = params.get("analysisId")
    if not isinstance(analysis_id, str) or not analysis_id:
        analysis_id = None
    ref = params.get("signalRef")
    if not isinstance(ref, dict):
        raise InvalidSignalError("params.signalRef 缺失")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    if not _warm_state["warm"]:
        # 核心会先预热；这里兜底提示，避免在 30 秒调用超时里做 150 秒初始化。
        return {
            "error": {
                "code": "engine_warming",
                "message": "Cardia 模型尚未预热，请先调用 warmup 并等待 /engine 就绪",
            }
        }

    samples = _read_signal(ref)
    try:
        signal = EcgSignal(
            samples=samples,
            fs=float(ref.get("fs") or 0),
            lead=str(ref.get("lead") or "unknown"),
            source="record",
        )
        analysis_options = AnalysisOptions(
            record_id=record_id,
            analysis_id=analysis_id,
            allow_short_record=bool(options.get("allowShortRecord", False)),
            tail_mode=str(options.get("tailMode", "pad")),
        )
        return analyze(signal, analysis_options)
    except InsufficientBeatsError as exc:
        return {"error": {"code": "too_few_beats", "message": str(exc)}}
    except InvalidSignalError as exc:
        return {"error": {"code": "invalid_signal", "message": str(exc)}}
    except ModelLoadError as exc:
        return {"error": {"code": "model_load_failed", "message": str(exc)}}


def _shrink_result(result: dict[str, Any], base: Path) -> dict[str, Any]:
    """结果过大时写临时文件，返回 ``resultRef``（宿主单行 JSON 上限 4MB）。"""
    blob = json.dumps(result, ensure_ascii=False).encode("utf-8")
    if len(blob) <= RESULT_INLINE_LIMIT_BYTES:
        return result
    path = base / f"{result.get('id', 'analysis')}.result.json"
    path.write_bytes(blob)
    return {
        "resultRef": {
            "path": str(path),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        }
    }


# ---------------------------------------------------------------------- 分发
def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "Cardia 2.0",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "analyze", "deactivate"],
            "health": health_payload(),
            "model": {
                "id": "cardia-2.0",
                "version": "2.0.0",
                "task": "beat-classification",
                "classes": ["N", "SVEB", "VEB", "F"],
            },
        }
    if method == "warmup":
        start_warmup()
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "analyze":
        result = _analyze(params)
        if "error" in result:
            return result
        ref = params.get("signalRef") if isinstance(params.get("signalRef"), dict) else {}
        base = Path(str(ref.get("path") or "")).parent
        if not base.is_dir():
            base = Path(os.environ.get("TEMP") or ".")
        return _shrink_result(result, base)
    if method in {"activate"}:
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
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _error(None, RpcError(-32700, "parse error"))
            continue
        if not isinstance(message, dict) or "method" not in message:
            continue
        if "id" not in message:
            continue  # notification：Cardia 不发通知，也不处理
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

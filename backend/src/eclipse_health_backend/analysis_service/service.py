"""核心分析服务：发起分析、串行执行、落库、引擎状态。

设计要点：

- ``POST`` 只做同步校验（记录/信号）并立刻返回 ``202``，真正的分析在后台线程执行；
- 全进程串行（一条队列一个线程），保证「同一记录串行分析」且模块调用不会互相抢占；
- 波形通过临时 float32 文件交给模块，绝不塞进 JSON（契约 §5）；
- 模块不可用时可用 ``EH_ANALYSIS_DIRECT=1`` 走同进程直调，便于调试与兜底；
- 引擎预热在后台线程做，HTTP 就绪不被 150 秒的 ONNX 初始化阻塞。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..analysis.ids import rfc3339
from ..analysis.types import (
    AnalysisError,
    AnalysisOptions,
    EcgSignal,
    InsufficientBeatsError,
    InvalidSignalError,
    ModelLoadError,
)
from ..db import analysis_repo
from ..db.base import session_scope
from ..db.repositories import (
    get_record_row,
    list_signal_rows,
    record_from_row,
    signal_from_row,
)
from ..domain.common import utc_now
from ..modules.errors import ModuleError
from ..settings import get_settings
from ..storage.files import read_signal, sha256_hex
from .bridge import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    CARDIA_SOURCE_DIR,
    CardiaBridge,
)

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}


class JobError(Exception):
    """分析作业的业务错误（会落库为 ``status=failed`` + ``error``）。"""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class EngineState:
    status: str = "warming"
    engine: str = CARDIA_ENGINE
    module_id: str = CARDIA_MODULE_ID
    model_id: str = CARDIA_MODEL_ID
    model_version: str = CARDIA_MODEL_VERSION
    message: str = "正在后台预热 Cardia 模型"
    started_at: datetime | None = None
    ready_at: datetime | None = None
    warmup_seconds: float | None = None
    mode: str = "module"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "engine": self.engine,
            "moduleId": self.module_id,
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "message": self.message,
            "startedAt": rfc3339(self.started_at) if self.started_at else None,
            "readyAt": rfc3339(self.ready_at) if self.ready_at else None,
            "warmupSeconds": self.warmup_seconds,
            "mode": self.mode,
            "error": self.error,
            **self.extra,
        }


def _warm_message(seconds: float | None) -> str:
    if seconds is None:
        return "Cardia 模型已就绪"
    return f"Cardia 模型已就绪（预热耗时 {seconds:.1f} 秒）"


class AnalysisService:
    """后台分析队列 + 引擎预热状态机。线程安全。"""

    def __init__(
        self,
        *,
        direct: bool | None = None,
        manager_factory: Callable[[], Any] | None = None,
        auto_install: bool | None = None,
        warm_timeout_s: float | None = None,
        start_warmup: bool | None = None,
    ) -> None:
        self.direct = _env_flag("EH_ANALYSIS_DIRECT", False) if direct is None else direct
        self.auto_install = (
            _env_flag("EH_CARDIA_AUTO_INSTALL", True) if auto_install is None else auto_install
        )
        self.warm_timeout_s = warm_timeout_s or float(
            os.environ.get("EH_CARDIA_WARM_TIMEOUT", "900")
        )
        self.state = EngineState(mode="direct" if self.direct else "module")
        self.state.extra["modelCard"] = _load_model_card()
        self._manager_factory = manager_factory or _default_manager_factory
        self._bridge = CardiaBridge(
            self._manager_factory,
            auto_install=self.auto_install,
            warm_timeout_s=self.warm_timeout_s,
        )

        self._lock = threading.RLock()
        self._submit_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._warm_thread: threading.Thread | None = None
        self._warm_reason = "启动预热"

        self._queue: queue.Queue[str | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._closing = False

        self.recover_stale()

        if start_warmup is None:
            start_warmup = _autostart_default()
        if start_warmup:
            self.start()

    def recover_stale(self) -> int:
        """进程重启后，把遗留的 queued/running 分析标记为 failed(interrupted)。

        否则这些行会一直占住「同记录串行」的幂等判断，用户再次点击只会拿回
        一条永远不动的分析。
        """
        try:
            from sqlmodel import select

            from ..db.models import AnalysisTable as _AnalysisTable

            with session_scope() as session:
                rows = list(
                    session.exec(
                        select(_AnalysisTable).where(
                            _AnalysisTable.status.in_(("queued", "running"))
                        )
                    )
                )
                for row in rows:
                    analysis_repo.save_failure(
                        session,
                        row,
                        error={
                            "code": "interrupted",
                            "message": "服务重启，分析被中断，请重新发起",
                        },
                    )
                return len(rows)
        except Exception:
            logger.debug("stale analysis recovery skipped", exc_info=True)
            return 0

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        """启动预热线程（幂等）；HTTP 就绪不被阻塞。"""
        with self._lock:
            if self._closing:
                return
            if self._warm_thread is not None and self._warm_thread.is_alive():
                return
            if self.state.status == "ready":
                return
            self.state.status = "warming"
            self._ready_event.clear()
            self._warm_thread = threading.Thread(
                target=self._warm, name="cardia-warmup", daemon=True
            )
            self._warm_thread.start()

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
        self._queue.put(None)
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=5.0)
        warm = self._warm_thread
        if warm is not None and warm.is_alive():
            warm.join(timeout=1.0)

    # ------------------------------------------------------------------ 预热
    def _warm(self) -> None:
        started = utc_now()
        with self._lock:
            self.state.status = "warming"
            self.state.started_at = started
            self.state.ready_at = None
            self.state.error = None
            self.state.message = (
                "正在后台预热 Cardia 模型（首次加载 ONNX 会话较慢，仅一次；"
                f"原因：{self._warm_reason}）"
            )
        started_perf = time.perf_counter()
        try:
            if self.direct:
                self._warm_direct()
                seconds = time.perf_counter() - started_perf
            else:
                seconds = self._bridge.warmup()
            with self._lock:
                self.state.status = "ready"
                self.state.ready_at = utc_now()
                self.state.warmup_seconds = round(seconds, 3)
                self.state.message = _warm_message(self.state.warmup_seconds)
                self.state.error = None
            logger.info("cardia engine ready in %.1fs (%s)", seconds, self.state.mode)
        except Exception as exc:  # noqa: BLE001 - 预热失败必须变成可查询状态
            message = _describe_error(exc)
            with self._lock:
                self.state.status = "error"
                self.state.error = message
                self.state.warmup_seconds = round(time.perf_counter() - started_perf, 3)
                self.state.message = f"Cardia 模型预热失败：{message}"
            logger.warning("cardia engine warmup failed: %s", message)
        finally:
            self._ready_event.set()

    def _warm_direct(self) -> None:
        from ..analysis.model import prewarm

        info = prewarm()  # 初始化并缓存 ONNX 会话；不做推理
        with self._lock:
            self.state.extra["sessionInitSeconds"] = info.get("sessionInitSeconds")

    def _reset_warming(self, reason: str) -> None:
        with self._lock:
            if self.state.status == "ready":
                self.state.status = "warming"
            self._warm_reason = reason
        self.start()

    def _ensure_ready(self) -> None:
        if self.state.status == "ready":
            return
        self.start()
        self._ready_event.wait(timeout=self.warm_timeout_s)
        if self.state.status == "ready":
            return
        if self.state.status == "error":
            raise JobError(
                "engine_unavailable",
                self.state.error or "Cardia 引擎预热失败",
            )
        raise JobError("engine_unavailable", "Cardia 引擎仍在预热，暂时无法分析")

    def engine_status(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_dict()

    def start_warmup(self) -> None:
        self.start()

    # ------------------------------------------------------------------ 提交
    def submit(
        self,
        *,
        record_id: str,
        engine: str = CARDIA_ENGINE,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """创建（或复用）分析任务；返回 ``(accepted, reused)``。"""
        options = dict(options or {})
        with self._submit_lock, session_scope() as session:
            active = analysis_repo.find_active_row(session, record_id)
            if active is not None:
                return (
                    {
                        "analysisId": active.id,
                        "recordId": active.record_id,
                        "status": active.status,
                        "engine": (active.data or {}).get("engine", engine),
                    },
                    True,
                )
            row = analysis_repo.create_analysis(
                session,
                record_id=record_id,
                engine=engine,
                module_id=CARDIA_MODULE_ID,
                model_id=CARDIA_MODEL_ID,
                model_version=CARDIA_MODEL_VERSION,
            )
            data = dict(row.data)
            data["parameters"] = {"engine": engine, "options": options}
            row.data = data
            session.add(row)
            session.commit()
            accepted = {
                "analysisId": row.id,
                "recordId": record_id,
                "status": row.status,
                "engine": engine,
            }
        self._ensure_worker()
        self._queue.put(accepted["analysisId"])
        return accepted, False

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop, name="analysis-worker", daemon=True
            )
            self._worker.start()

    # ------------------------------------------------------------------ 执行
    def _worker_loop(self) -> None:
        while True:
            analysis_id = self._queue.get()
            if analysis_id is None:
                return
            try:
                self.run_once(analysis_id)
            except Exception:
                logger.exception("analysis job %s crashed outside handler", analysis_id)

    def run_once(self, analysis_id: str) -> None:
        """执行一条分析（同步；测试可直接调用）。"""
        with session_scope() as session:
            row = analysis_repo.get_analysis_row(session, analysis_id)
            if row is None or row.status not in ("queued", "running"):
                return
            record_id = row.record_id
            parameters = dict((row.data or {}).get("parameters") or {})
            options = dict(parameters.get("options") or {})
            analysis_repo.update_status(
                session,
                row,
                status="running",
                progress={"stage": "quality", "percent": 10},
                started_at=utc_now(),
            )

        temp_dir = get_settings().data_dir / "tmp" / "analyses" / analysis_id
        try:
            signal_ref = self._prepare_signal(record_id, analysis_id, temp_dir)
            self._set_progress(analysis_id, "inference", 40)
            result = self._analyze(signal_ref, analysis_id, options)
            self._set_progress(analysis_id, "measurements", 85)
            with session_scope() as session:
                row = analysis_repo.get_analysis_row(session, analysis_id)
                if row is None:
                    return
                analysis_repo.save_result(session, row, result)
        except JobError as exc:
            self._fail(analysis_id, exc.to_error())
        except ModuleError as exc:
            if exc.code in {"MODULE_CRASH", "MODULE_TIMEOUT"}:
                self._reset_warming("模块崩溃后重新预热")
            self._fail(analysis_id, _module_error_payload(exc))
        except InsufficientBeatsError as exc:
            self._fail(analysis_id, {"code": "too_few_beats", "message": str(exc)})
        except InvalidSignalError as exc:
            self._fail(analysis_id, {"code": "invalid_signal", "message": str(exc)})
        except ModelLoadError as exc:
            self._fail(analysis_id, {"code": "model_load_failed", "message": str(exc)})
        except AnalysisError as exc:
            self._fail(analysis_id, {"code": "analysis_failed", "message": str(exc)})
        except Exception as exc:
            logger.exception("analysis %s failed", analysis_id)
            self._fail(
                analysis_id,
                {"code": "analysis_failed", "message": f"{type(exc).__name__}: {exc}"[:300]},
            )
        finally:
            _cleanup_dir(temp_dir)

    def _prepare_signal(
        self, record_id: str, analysis_id: str, temp_dir: Path
    ) -> dict[str, Any]:
        with session_scope() as session:
            record_row = get_record_row(session, record_id)
            if record_row is None or record_row.deleted_at is not None:
                raise JobError("record_not_found", "记录不存在或已删除")
            signals = list_signal_rows(session, record_id)
            if not signals:
                raise JobError("record_has_no_signal", "记录没有波形，无法分析")
            signal_row = _pick_signal(signals)
            record = record_from_row(record_row)
            signal = signal_from_row(signal_row)
            relative_path = signal_row.relative_path
            expected_sha = signal_row.sha256
            n_samples = int(signal_row.n_samples)

        payload = read_signal(relative_path, expected_sha)
        digest = sha256_hex(payload)
        if digest != expected_sha:
            raise JobError("invalid_signal", "波形文件校验失败", {"path": relative_path})

        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"{analysis_id}.f32"
        path.write_bytes(payload)
        return {
            "recordId": record_id,
            "analysisId": analysis_id,
            "signalRef": {
                "path": str(path),
                "sha256": digest,
                "fs": signal.fs,
                "lead": signal.lead,
                "unit": signal.unit,
                "nSamples": n_samples,
                "durationSec": record.durationSec,
            },
        }

    def _analyze(
        self, signal_ref: dict[str, Any], analysis_id: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        allow_short = bool(options.get("allowShortRecord", False))
        tail_mode = str(options.get("tailMode", "pad"))
        request = {
            "recordId": signal_ref["recordId"],
            "analysisId": analysis_id,
            "signalRef": signal_ref["signalRef"],
            "options": {"allowShortRecord": allow_short, "tailMode": tail_mode},
        }
        self._ensure_ready()
        if self.direct:
            return self._analyze_direct(request)
        result = self._bridge.analyze(request)
        error = result.get("error")
        if isinstance(error, dict):
            raise JobError(
                str(error.get("code") or "analysis_failed"),
                str(error.get("message") or "分析失败"),
                error.get("details") if isinstance(error.get("details"), dict) else None,
            )
        if result.get("status") not in (None, "completed"):
            raise JobError("analysis_failed", "模块返回了未完成的分析结果")
        return result

    def _analyze_direct(self, request: dict[str, Any]) -> dict[str, Any]:
        from ..analysis.engine import analyze

        ref = request["signalRef"]
        path = Path(str(ref["path"]))
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise JobError("invalid_signal", "临时波形文件不可读") from exc
        if sha256_hex(blob) != ref["sha256"]:
            raise JobError("invalid_signal", "临时波形文件校验失败")
        samples = np.frombuffer(blob, dtype="<f4").astype(np.float32)
        signal = EcgSignal(
            samples=samples,
            fs=float(ref["fs"]),
            lead=str(ref["lead"]),
            source="record",
        )
        options = AnalysisOptions(
            record_id=request["recordId"],
            analysis_id=request["analysisId"],
            allow_short_record=bool(request["options"].get("allowShortRecord", False)),
            tail_mode=str(request["options"].get("tailMode", "pad")),
        )
        return analyze(signal, options)

    def _set_progress(self, analysis_id: str, stage: str, percent: int) -> None:
        with session_scope() as session:
            row = analysis_repo.get_analysis_row(session, analysis_id)
            if row is None or row.status != "running":
                return
            analysis_repo.update_status(
                session, row, status="running", progress={"stage": stage, "percent": percent}
            )

    def _fail(self, analysis_id: str, error: dict[str, Any]) -> None:
        with session_scope() as session:
            row = analysis_repo.get_analysis_row(session, analysis_id)
            if row is None:
                return
            analysis_repo.save_failure(session, row, error=error)


def _pick_signal(signals: list[Any]) -> Any:
    """单导联优先 MLII（模型训练导联），否则取最早写入的一条。"""
    for row in signals:
        if str(row.lead).upper() == "MLII":
            return row
    return signals[0]


def _module_error_payload(exc: ModuleError) -> dict[str, Any]:
    mapping = {
        "MODULE_CRASH": "module_crash",
        "MODULE_TIMEOUT": "module_timeout",
        "MODEL_LOAD_FAILED": "model_load_failed",
        "RESOURCE_EXCEEDED": "resource_exceeded",
        "PERMISSION_DENIED": "permission_denied",
        "MODULE_DISABLED": "module_disabled",
        "INVALID_INPUT": "invalid_signal",
    }
    return {
        "code": mapping.get(exc.code, "analysis_failed"),
        "message": exc.message or "模块调用失败",
        "details": {"moduleCode": exc.code, **(exc.detail or {})},
    }


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, ModuleError):
        return f"{exc.code}: {exc.message}"
    return f"{type(exc).__name__}: {exc}"[:300]


def _load_model_card() -> dict[str, Any] | None:
    """从模块 manifest 读模型卡摘要（``GET /engine`` 暴露，UI 直接渲染）。"""
    path = CARDIA_SOURCE_DIR / "module.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    models = (raw.get("contributes") or {}).get("models") or []
    if not models or not isinstance(models[0], dict):
        return None
    card = models[0]
    model_card = card.get("modelCard") or {}
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "parameters": model_card.get("parameters"),
        "trainingData": model_card.get("trainingData"),
        "classes": (card.get("output") or {}).get("classes"),
        "input": card.get("input"),
        "limitations": model_card.get("limitations") or [],
        "nonDiagnostic": model_card.get("nonDiagnostic", True),
        "license": model_card.get("license"),
    }


def _cleanup_dir(path: Path) -> None:
    try:
        for child in path.glob("*"):
            child.unlink(missing_ok=True)
        path.rmdir()
    except OSError:
        pass


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _autostart_default() -> bool:
    """生产启动即后台预热；测试进程不自动预热，避免拖慢其他测试套件。

    测试里需要真实引擎时显式 ``AnalysisService(start_warmup=True)`` 或
    ``EH_CARDIA_PREWARM=1``。
    """
    if not _env_flag("EH_CARDIA_PREWARM", True):
        return False
    return not os.environ.get("PYTEST_CURRENT_TEST")


# ---------------------------------------------------------------------- 单例
_service_lock = threading.Lock()
_service: AnalysisService | None = None


def _default_manager_factory() -> Any:
    from ..modules.api import get_manager

    return get_manager()


def init_analysis_service(**kwargs: Any) -> AnalysisService:
    """由 ``app.py`` lifespan 调用；重复调用会替换旧实例。"""
    global _service
    with _service_lock:
        if _service is not None:
            _service.shutdown()
        _service = AnalysisService(**kwargs)
        return _service


def get_analysis_service() -> AnalysisService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = AnalysisService()
    return _service


def set_analysis_service(service: AnalysisService | None) -> None:
    """测试用：注入替身或清理单例。"""
    global _service
    with _service_lock:
        _service = service


def shutdown_analysis_service() -> None:
    global _service
    with _service_lock:
        if _service is not None:
            _service.shutdown()
            _service = None


__all__ = [
    "AnalysisService",
    "EngineState",
    "JobError",
    "get_analysis_service",
    "init_analysis_service",
    "set_analysis_service",
    "shutdown_analysis_service",
]

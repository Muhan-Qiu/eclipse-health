"""Cardia 2.0 模型加载与前向。

只加载发布权重（ONNX），不包含训练代码。模型从字节加载，避免 Windows 中文路径
下 ``InferenceSession(path)`` 的问题。会话按文件哈希缓存，整个进程只初始化一次。

模型选择（不改推理数学）：

- 默认优先 ``cardia_k4_best_sim.onnx``（onnxsim 固定形状产物，初始化 ~1.5s）；
  文件缺失时回退 ``cardia_k4_best.onnx``（原图，初始化 ~150s）。
- ``EH_CARDIA_MODEL=original`` 强制原图；``EH_CARDIA_MODEL_PATH`` 指向任意权重文件
  （Cardia 模块用它加载模块自带的简化权重）。
- 两者都只影响“加载哪个文件”，预处理与推理公式不变。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .types import (
    DEFAULT_MODEL_DIR,
    InsufficientBeatsError,
    ModelLoadError,
)

_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, Any] = {}
# 每个模型文件的 ONNX 会话初始化耗时（秒），供 /engine 与报告使用。
_SESSION_INIT_SECONDS: dict[str, float] = {}

MODEL_ENV = "EH_CARDIA_MODEL"
MODEL_PATH_ENV = "EH_CARDIA_MODEL_PATH"
ORIGINAL_MODEL_FILE = "cardia_k4_best.onnx"
SIMPLIFIED_MODEL_FILE = "cardia_k4_best_sim.onnx"

# EH_CARDIA_MODEL 的取值；未设置 / sim / 未知取值都按 auto（简化图优先）。
_ORIGINAL_CHOICES = {"original", "orig", "baseline"}

_OPT_LEVELS = {
    "all": "ORT_ENABLE_ALL",
    "basic": "ORT_ENABLE_BASIC",
    "extended": "ORT_ENABLE_EXTENDED",
    "disabled": "ORT_DISABLE_ALL",
    "disable": "ORT_DISABLE_ALL",
    "off": "ORT_DISABLE_ALL",
}


@dataclass(frozen=True)
class ModelInfo:
    model_dir: Path
    model_path: Path
    preprocess_path: Path
    model_sha256: str
    preprocess_sha256: str
    preprocess: dict[str, Any]
    # "onnx-simplified"（固定形状简化图）或 "onnx"（原图）；只标注来源，不改数值。
    model_variant: str = "onnx"


def _variant_name(path: Path) -> str:
    return "onnx-simplified" if path.name == SIMPLIFIED_MODEL_FILE else "onnx"


def resolve_model_path(
    model_dir: str | Path,
    model_path: str | Path | None = None,
) -> Path:
    """按「显式参数 → 环境变量 → 简化图 → 原图」选择权重文件。

    - ``model_path`` 参数：调用方指定，优先级最高（测试/调试用）；
    - ``EH_CARDIA_MODEL=original``：强制原图；
    - ``EH_CARDIA_MODEL_PATH``：任意权重文件（模块自带简化权重走这里），
      文件不存在则忽略；
    - 其余情况：``model_dir`` 下存在简化图就用简化图，否则原图。
    """
    model_dir = Path(model_dir)
    if model_path is not None:
        return Path(model_path)

    choice = os.environ.get(MODEL_ENV, "").strip().lower()
    if choice in _ORIGINAL_CHOICES:
        return model_dir / ORIGINAL_MODEL_FILE

    explicit = os.environ.get(MODEL_PATH_ENV, "").strip()
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate

    simplified = model_dir / SIMPLIFIED_MODEL_FILE
    # sim / 留空 / 未知取值都按 auto：简化图优先，缺失回退原图（拼写错误不至于起不来）。
    return simplified if simplified.is_file() else model_dir / ORIGINAL_MODEL_FILE


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _read_bytes(path: Path, what: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ModelLoadError(f"无法读取{what} {path}：{exc}") from exc


def read_preprocess(model_dir: str | Path | None = None) -> dict[str, Any]:
    """只读 preprocess.json；短记录判定等场景不需要初始化 ONNX 会话。"""
    model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
    blob = _read_bytes(model_dir / "preprocess.json", "预处理配置")
    try:
        return json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelLoadError(f"preprocess.json 解析失败：{exc}") from exc


def _session_options(ort: Any) -> Any:
    """会话参数可用环境变量微调（数值不受影响；见 reports/B2-01-ort-spike.md）。

    - ``EH_ORT_OPT_LEVEL``：all|extended|basic|disabled，默认 all；
    - ``EH_ORT_INTRA_THREADS`` / ``EH_ORT_INTER_THREADS``：默认交给 ORT。
    实测本机 24k 节点模型初始化 140–200 秒，与优化级别/线程数无关。
    """
    options = ort.SessionOptions()
    level = _OPT_LEVELS.get(os.environ.get("EH_ORT_OPT_LEVEL", "all").strip().lower(), "ORT_ENABLE_ALL")
    options.graph_optimization_level = getattr(ort.GraphOptimizationLevel, level)
    for env_name, attr in (
        ("EH_ORT_INTRA_THREADS", "intra_op_num_threads"),
        ("EH_ORT_INTER_THREADS", "inter_op_num_threads"),
    ):
        raw = os.environ.get(env_name)
        if raw and raw.strip().isdigit():
            setattr(options, attr, max(1, int(raw)))
    options.log_severity_level = 3
    return options


def _get_session(model_path: Path, model_sha256: str, blob: bytes) -> Any:
    """进程级缓存；ORT 会话初始化很慢，绝不重复建。"""
    with _SESSION_LOCK:
        session = _SESSIONS.get(model_sha256)
        if session is not None:
            return session
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ModelLoadError("缺少 onnxruntime 依赖") from exc

        options = _session_options(ort)
        started = time.perf_counter()
        try:
            session = ort.InferenceSession(
                blob,
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise ModelLoadError(f"ONNX 会话初始化失败：{exc}") from exc
        _SESSION_INIT_SECONDS[model_sha256] = time.perf_counter() - started
        _SESSIONS[model_sha256] = session
        return session


def _static_batch_size(input_meta: Any) -> int | None:
    """输入第 0 维是具体整数时返回它；符号维（dynamic batch）返回 None。"""
    try:
        dim = input_meta.shape[0]
    except (IndexError, TypeError):
        return None
    return dim if isinstance(dim, int) and dim > 0 else None


class CardiaModel:
    """预处理参数 + ONNX 会话。"""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        model_path: str | Path | None = None,
    ) -> None:
        model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
        resolved_path = resolve_model_path(model_dir, model_path)
        preprocess_path = model_dir / "preprocess.json"
        config_path = model_dir / "model_config.json"

        model_blob = _read_bytes(resolved_path, "模型")
        preprocess_blob = _read_bytes(preprocess_path, "预处理配置")
        try:
            preprocess = json.loads(preprocess_blob.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelLoadError(f"preprocess.json 解析失败：{exc}") from exc

        self.info = ModelInfo(
            model_dir=model_dir,
            model_path=resolved_path,
            preprocess_path=preprocess_path,
            model_sha256=_sha256(model_blob),
            preprocess_sha256=_sha256(preprocess_blob),
            preprocess=preprocess,
            model_variant=_variant_name(resolved_path),
        )
        self._validate(preprocess, config_path)

        self.sequence_length = int(preprocess.get("sequence_length", 64))
        self.stride = int(preprocess.get("stride", self.sequence_length))
        self.class_order = [str(c) for c in preprocess["class_order"]]
        self.dt_median = float(preprocess["dt_median"])
        self.mean = np.asarray(preprocess["scaler_mean"], dtype=np.float64)
        self.scale = np.asarray(preprocess["scaler_scale"], dtype=np.float64)

        self.session = _get_session(resolved_path, self.info.model_sha256, model_blob)
        inputs = list(self.session.get_inputs())
        if len(inputs) < 2:
            raise ModelLoadError("ONNX 模型缺少 x/dt 输入")
        names = [item.name for item in inputs]
        self._x_name = "x" if "x" in names else names[0]
        self._dt_name = "dt" if "dt" in names else names[1]
        # 简化图是固定形状（batch=1）；批量窗口需要拆成单窗口前向。
        self._fixed_batch = _static_batch_size(
            next(item for item in inputs if item.name == self._x_name)
        )

    @staticmethod
    def _validate(preprocess: dict[str, Any], config_path: Path) -> None:
        required = ("scaler_mean", "scaler_scale", "dt_median", "class_order")
        missing = [key for key in required if key not in preprocess]
        if missing:
            raise ModelLoadError(f"preprocess.json 缺少字段：{', '.join(missing)}")
        if len(preprocess["scaler_mean"]) != len(preprocess["scaler_scale"]):
            raise ModelLoadError("scaler_mean 与 scaler_scale 长度不一致")
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                config = {}
            if config.get("class_order") and list(config["class_order"]) != list(
                preprocess["class_order"]
            ):
                raise ModelLoadError(
                    "model_config.json 与 preprocess.json 的类别顺序不一致"
                )

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        z = np.asarray(logits, dtype=np.float64)
        z = z - z.max(axis=-1, keepdims=True)
        exp = np.exp(z)
        return exp / exp.sum(axis=-1, keepdims=True)

    def _forward(self, x: np.ndarray, dt: np.ndarray) -> np.ndarray:
        feeds = {
            self._x_name: x.astype(np.float32),
            self._dt_name: dt.astype(np.float32),
        }
        return self.session.run(None, feeds)[0]

    def _forward_chunks(self, x: np.ndarray, dt: np.ndarray) -> np.ndarray:
        step = self._fixed_batch
        if step is None:
            try:
                return self._forward(x, dt)
            except Exception:  # noqa: BLE001 - 退化路径，任何前向失败都逐块重试
                # 某些导出只接受 batch=1；逐块前向，结果与批量一致。
                step = 1
        if len(x) <= step:
            return self._forward(x, dt)
        outputs = [
            self._forward(x[start : start + step], dt[start : start + step])
            for start in range(0, len(x), step)
        ]
        return np.concatenate(outputs, axis=0)

    def predict(
        self,
        features: np.ndarray,
        pre_r: np.ndarray,
        *,
        allow_short: bool = False,
        tail_mode: str = "pad",
    ) -> tuple[np.ndarray, np.ndarray]:
        """返回 ``(probs [n,4], covered [n])``；未覆盖的尾搏只在 drop 模式出现。"""
        features = np.asarray(features, dtype=np.float64)
        pre_r = np.asarray(pre_r, dtype=np.float64).ravel()
        n = len(features)
        if n == 0:
            raise InsufficientBeatsError("没有有效心搏，无法推理")
        if n != len(pre_r):
            raise InsufficientBeatsError("特征与 RR 间期数量不一致")
        if features.shape[1] != len(self.mean):
            raise InsufficientBeatsError(
                f"特征维度 {features.shape[1]} 与模型 {len(self.mean)} 不一致"
            )

        x_all = (features - self.mean) / self.scale
        dt_all = pre_r / self.dt_median
        t = self.sequence_length

        probs = np.zeros((n, 4), dtype=np.float64)
        covered = np.zeros(n, dtype=bool)

        if n < t:
            if not allow_short:
                raise InsufficientBeatsError(
                    f"有效心搏只有 {n} 个（<{t}），无法组成预测输入；"
                    "短记录请显式设置 allow_short_record=True 以零填充"
                )
            x_pad = np.zeros((1, t, x_all.shape[1]), dtype=np.float64)
            dt_pad = np.ones((1, t), dtype=np.float64)
            x_pad[0, :n] = x_all
            dt_pad[0, :n] = dt_all
            probs[:n] = self._softmax(self._forward_chunks(x_pad, dt_pad))[0, :n]
            covered[:n] = True
            return probs, covered

        starts = list(range(0, n - t + 1, self.stride))
        chunks = [x_all[s : s + t] for s in starts]
        dt_chunks = [dt_all[s : s + t] for s in starts]
        tail = n - (starts[-1] + t)
        add_tail = tail > 0 and tail_mode == "pad"
        if add_tail:
            # 用最后一窗左移覆盖尾部，保持相同 Δt 语义（见 preprocess.json note）。
            chunks.append(x_all[n - t : n])
            dt_chunks.append(dt_all[n - t : n])

        x_batch = np.stack(chunks, axis=0)
        dt_batch = np.stack(dt_chunks, axis=0)
        chunk_probs = self._softmax(self._forward_chunks(x_batch, dt_batch))

        for ci, start in enumerate(starts):
            probs[start : start + t] = chunk_probs[ci]
            covered[start : start + t] = True
        if add_tail:
            probs[n - tail : n] = chunk_probs[-1][-tail:]
            covered[n - tail : n] = True
        return probs, covered


def session_init_seconds(model_sha256: str) -> float | None:
    """该模型文件在本进程的 ONNX 会话初始化耗时（秒）；未初始化返回 None。"""
    return _SESSION_INIT_SECONDS.get(model_sha256)


def prewarm(
    model_dir: str | Path | None = None,
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """预热 ONNX 会话（首次会阻塞到初始化完成），返回模型标识与耗时。

    不跑推理、不改任何数值；供后台预热线程与 ``GET /engine`` 使用。
    """
    started = time.perf_counter()
    known_before = set(_SESSIONS)
    model = CardiaModel(model_dir, model_path)
    sha = model.info.model_sha256
    init_seconds = _SESSION_INIT_SECONDS.get(sha)
    return {
        "modelId": "cardia-2.0",
        "modelSha256": sha,
        "modelFile": model.info.model_path.name,
        "modelVariant": model.info.model_variant,
        "sequenceLength": model.sequence_length,
        "sessionInitSeconds": round(init_seconds, 3) if init_seconds is not None else None,
        "callSeconds": round(time.perf_counter() - started, 3),
        "cached": sha in known_before,
    }

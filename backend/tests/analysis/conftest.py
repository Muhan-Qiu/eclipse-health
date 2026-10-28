"""B1-03 分析引擎测试夹具。

模型会话初始化很慢（本机约 160s），所以所有夹具都是 session 级，
整个 pytest 进程只加载一次 ONNX。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from eclipse_health_backend.analysis import AnalysisOptions, analyze, load_wfdb
from eclipse_health_backend.analysis.model import CardiaModel
from eclipse_health_backend.analysis.types import EcgSignal

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = BACKEND_ROOT / "resources" / "samples"
MODEL_DIR = BACKEND_ROOT / "resources" / "models" / "cardia"
V2_DIR = (
    BACKEND_ROOT.parent.parent / "V2" / "发布预权重与评分信息" / "推理代码"
)


def make_synthetic_ecg(
    *,
    fs: float = 500.0,
    duration: float = 80.0,
    heart_rate: float = 72.0,
    noise: float = 0.01,
    seed: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    """合成单导联 ECG（mV）：P/QRS/T 高斯波 + 白噪声。"""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * duration)) / fs
    signal = np.zeros_like(t)
    rr = 60.0 / heart_rate
    beat_times = np.arange(0.5, duration - 0.5, rr)
    for beat in beat_times:
        signal += 1.0 * np.exp(-(((t - beat) / 0.015) ** 2))
        signal += 0.10 * np.exp(-(((t - (beat - 0.16)) / 0.03) ** 2))
        signal += 0.20 * np.exp(-(((t - (beat + 0.25)) / 0.06) ** 2))
    signal += rng.normal(0.0, noise, signal.shape)
    return signal, beat_times


def _load_v2_module(name: str, filename: str):
    path = V2_DIR / filename
    if not path.exists():
        pytest.skip(f"V2 参考实现不存在：{path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        pytest.skip(f"无法加载 V2 参考实现：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def synthetic_ecg():
    return make_synthetic_ecg


@pytest.fixture(scope="session")
def v2_feature_module():
    return _load_v2_module("v2_feature_extract", "feature_extract.py")


@pytest.fixture(scope="session")
def v2_inference_module():
    return _load_v2_module("v2_inference", "inference.py")


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def model_dir() -> Path:
    return MODEL_DIR


@pytest.fixture(scope="session")
def cardia_model(model_dir: Path) -> CardiaModel:
    return CardiaModel(model_dir)


@pytest.fixture(scope="session")
def signal_100() -> EcgSignal:
    return load_wfdb(SAMPLES_DIR / "100")


@pytest.fixture(scope="session")
def signal_200() -> EcgSignal:
    return load_wfdb(SAMPLES_DIR / "200")


@pytest.fixture(scope="session")
def signal_208() -> EcgSignal:
    return load_wfdb(SAMPLES_DIR / "208")


@pytest.fixture(scope="session")
def analysis_100(signal_100: EcgSignal) -> dict:
    return analyze(signal_100, AnalysisOptions(record_id="rec_test_100"))


@pytest.fixture(scope="session")
def analysis_200(signal_200: EcgSignal) -> dict:
    return analyze(signal_200, AnalysisOptions(record_id="rec_test_200"))


@pytest.fixture(scope="session")
def analysis_208(signal_208: EcgSignal) -> dict:
    return analyze(signal_208, AnalysisOptions(record_id="rec_test_208"))

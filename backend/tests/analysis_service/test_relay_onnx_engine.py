"""V4.2 · relay-v1 逐搏 ONNX 管线回归测试。

不依赖真实 relay 权重：用一个假 ORT 会话检查 manifest 声明是否被正确执行，
覆盖单导联复制、R 峰切窗、逐导联 z-score、64 搏序列、dt 第二输入和输出展平。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from eclipse_health_backend.analysis_service.engines import (
    ModuleModelSpec,
    _unsupported_reason,
)
from eclipse_health_backend.analysis_service.onnx_engine import (
    OnnxEngineError,
    OnnxEngineRunner,
)

CLASSES = ["N", "SVEB", "VEB", "F", "Q"]
MODULE_ID = "org.eclipsehealth.relay-ecg"


def _relay_model(mode: str) -> dict[str, Any]:
    sequence = mode == "sequence"
    x_shape = [1, 64, 2, 234] if sequence else [1, 2, 234]
    tensors: dict[str, Any] = {"x": {"dtype": "float32", "shape": x_shape}}
    if sequence:
        tensors["dt"] = {"dtype": "float32", "shape": [1, 64]}
    return {
        "id": "relay-k2" if sequence else "resnet1d",
        "name": "Relay test",
        "task": "ecg-beat-classification",
        "format": "onnx",
        "files": [{"path": "models/model.onnx", "sha256": "0" * 64}],
        "input": {
            "mode": mode,
            "fs": 360,
            "leads": 2,
            "windowSamples": 234,
            "windowBefore": 90,
            "windowAfter": 144,
            "beatsPerWindow": 64 if sequence else 1,
            "zscorePerLead": True,
            "dtMedianSeconds": 275.0 / 360.0,
            "tensors": tensors,
        },
        "output": {"tensor": "logits", "classes": CLASSES, "shape": [1, 64, 5] if sequence else [1, 5]},
        "preprocess": {
            "pipeline": "relay-v1-beat-window",
            "fs": 360,
            "windowBeforeSeconds": 0.25,
            "windowAfterSeconds": 0.4,
            "zscore": "per-lead",
            "dt": "rr_seconds / (275/360)",
        },
    }


def _spec(mode: str) -> ModuleModelSpec:
    model = _relay_model(mode)
    return ModuleModelSpec(
        engine_id=f"{MODULE_ID}:{model['id']}",
        module_id=MODULE_ID,
        module_version="0.1.0",
        module_dir=Path("."),
        model_id=str(model["id"]),
        model_name="Relay test",
        model=model,
        model_path=Path("unused.onnx"),
        model_relative_path="models/model.onnx",
        model_sha256="0" * 64,
    )


class _FakeInput:
    def __init__(self, name: str, shape: list[int]) -> None:
        self.name = name
        self.shape = shape
        self.type = "tensor(float)"


class _FakeOutput(_FakeInput):
    pass


class _FakeSession:
    def __init__(self, inputs: list[tuple[str, list[int]]], output_shape: list[int]) -> None:
        self._inputs = [_FakeInput(name, shape) for name, shape in inputs]
        self._outputs = [_FakeOutput("logits", output_shape)]
        self.calls: list[dict[str, tuple[int, ...]]] = []

    def get_inputs(self) -> list[_FakeInput]:
        return self._inputs

    def get_outputs(self) -> list[_FakeOutput]:
        return self._outputs

    def run(self, _names: Any, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.calls.append({key: value.shape for key, value in feed.items()})
        shape = self._outputs[0].shape
        if len(shape) == 3:
            count, classes = shape[1], shape[2]
            logits = np.tile(
                np.asarray([0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0], np.float32)[:classes],
                (count, 1),
            )
            return [logits[None, ...]]
        classes = shape[-1]
        logits = np.asarray([0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0], np.float32)[:classes]
        return [logits[None, :]]


def _samples(length: int = 2400) -> np.ndarray:
    # 非恒定波形，便于质量评估；R 峰位置在测试中直接注入。
    return np.sin(np.linspace(0, 40 * np.pi, length)).astype(np.float32)


def _positions(count: int) -> np.ndarray:
    return np.arange(120, 120 + count * 20, 20, dtype=np.int64)


def test_sequence_pipeline_feeds_4d_x_and_dt(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession([("x", [1, 64, 2, 234]), ("dt", [1, 64])], [1, 64, 5])
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._session_for",
        lambda _spec: session,
    )
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._detect_rpeaks",
        lambda _signal, _fs: _positions(80),
    )

    result = OnnxEngineRunner(_spec("sequence")).analyze(
        record_id="rec_test",
        analysis_id="ana_test",
        samples=_samples(),
        fs=360.0,
        lead="I",
    )

    assert len(session.calls) == 1
    assert session.calls[0]["x"] == (1, 64, 2, 234)
    assert session.calls[0]["dt"] == (1, 64)
    assert result["status"] == "completed"
    assert result["parameters"]["beatsScored"] == 64
    assert result["parameters"]["beatsDropped"] == 16
    assert result["parameters"]["sequences"] == 1
    assert result["provenance"]["preprocess"]["leads"] == 2
    assert result["provenance"]["preprocess"]["windowSamples"] == 234
    assert result["provenance"]["preprocess"]["beatsPerWindow"] == 64
    codes = {item["code"] for item in result["warnings"]}
    assert {"single_lead_duplicated", "tail_beats_dropped"} <= codes
    assert "wearable_limited_accuracy" in codes
    assert result["parameters"]["outOfDistribution"] is True
    probability_measurements = [
        item
        for item in result["measurements"]
        if ".class_probability." in str(item["code"])
    ]
    assert len(probability_measurements) == len(CLASSES)
    total = sum(float(item["value"]) for item in probability_measurements)
    assert abs(total - 100.0) < 0.01
    assert (
        max(probability_measurements, key=lambda item: item["value"])["label"]
        == "Q 概率"
    )
    # 心率 / HRV / 质量 / 异常占比与 Cardia 使用同一套测量口径。
    codes = {item["code"] for item in result["measurements"]}
    assert {
        "heart_rate_mean",
        "heart_rate_min",
        "heart_rate_max",
        "rr_mean",
        "sdnn",
        "rmssd",
        "pnn50",
        "n_ratio",
        "svb_ratio",
        "veb_ratio",
        "f_ratio",
    } <= codes
    assert result["quality"] is not None
    assert 0.0 <= result["quality"]["score"] <= 1.0
    assert result["parameters"]["nBeatsClassified"] == 64
    assert result["parameters"]["nBeatsDetected"] == 80
    assert result["summary"].startswith("平均心率")


def test_beat_pipeline_feeds_3d_single_beat(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession([("x", [1, 2, 234])], [1, 5])
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._session_for",
        lambda _spec: session,
    )
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._detect_rpeaks",
        lambda _signal, _fs: _positions(5),
    )

    result = OnnxEngineRunner(_spec("beat")).analyze(
        record_id="rec_test",
        analysis_id="ana_test",
        samples=_samples(),
        fs=360.0,
        lead="I",
    )

    assert len(session.calls) == 5
    assert all(call["x"] == (1, 2, 234) for call in session.calls)
    assert result["parameters"]["beatsScored"] == 5
    assert result["parameters"]["beatsDropped"] == 0
    assert result["parameters"]["sequences"] == 0


def test_sequence_needs_enough_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession([("x", [1, 64, 2, 234]), ("dt", [1, 64])], [1, 64, 5])
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._session_for",
        lambda _spec: session,
    )
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._detect_rpeaks",
        lambda _signal, _fs: _positions(10),
    )

    with pytest.raises(OnnxEngineError) as caught:
        OnnxEngineRunner(_spec("sequence")).analyze(
            record_id="rec_test",
            analysis_id="ana_test",
            samples=_samples(),
            fs=360.0,
            lead="I",
        )
    assert caught.value.code == "too_few_beats"
    assert "至少 64" in caught.value.message
    assert session.calls == []


def test_output_class_mismatch_is_readable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession([("x", [1, 64, 2, 234]), ("dt", [1, 64])], [1, 64, 3])
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._session_for",
        lambda _spec: session,
    )
    monkeypatch.setattr(
        "eclipse_health_backend.analysis_service.onnx_engine._detect_rpeaks",
        lambda _signal, _fs: _positions(64),
    )

    with pytest.raises(OnnxEngineError) as caught:
        OnnxEngineRunner(_spec("sequence")).analyze(
            record_id="rec_test",
            analysis_id="ana_test",
            samples=_samples(),
            fs=360.0,
            lead="I",
        )
    assert caught.value.code == "engine_error"
    assert "类别数 5" in caught.value.message


def test_sleep_models_are_marked_unavailable_for_ecg() -> None:
    assert _unsupported_reason({"task": "sleep-staging"}) is not None
    assert _unsupported_reason({"task": "ecg-beat-classification"}) is None
    assert _unsupported_reason({"input": {"kind": "features-dt"}}) is not None
    assert _unsupported_reason({"task": "classification"}) is None

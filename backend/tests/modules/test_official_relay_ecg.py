"""官方模块 org.eclipsehealth.relay-ecg 的 manifest、适配层与 worker 测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "relay-ecg"
MAIN = MODULE_DIR / "src" / "main.py"
INDEX = MODULE_DIR / "models" / "index.json"
WEIGHTS = ROOT / "uploads" / "relay-ecg" / "models"
SAMPLE = ROOT / "backend" / "resources" / "samples" / "100"
FILES = [
    "relay_k2.onnx",
    "relay_k12.onnx",
    "relay_k4.onnx",
    "relay_k8.onnx",
    "bilstm.onnx",
    "resnet1d.onnx",
    "tlstm.onnx",
]


def _load_adapter():
    spec = importlib.util.spec_from_file_location("relay_ecg_adapter", MODULE_DIR / "src" / "adapter.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(lines: list[dict], weights_dir: str | None = None) -> list[dict]:
    env = os.environ.copy()
    env["EH_RELAY_MODELS_DIR"] = weights_dir or str(WEIGHTS)
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n"
    proc = subprocess.run(
        [sys.executable, str(MAIN)],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=180,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]


def test_manifest_matches_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["id"] == "org.eclipsehealth.relay-ecg"
    assert manifest["type"] == "analysis-model"
    assert manifest["permissions"] == ["records:read"]
    assert {"numpy", "onnxruntime", "wfdb"} <= set(manifest["dependencies"])

    models = manifest["contributes"]["models"]
    assert len(models) == 7
    index_ids = {item["id"] for item in json.loads(INDEX.read_text(encoding="utf-8"))["models"]}
    assert {item["id"] for item in models} == index_ids
    for item in models:
        assert item["format"] == "onnx"
        assert item["modelCard"]["nonDiagnostic"] is True
        assert len(item["files"]) == 1
        assert item["files"][0]["path"].startswith("models/")

    ui = manifest["contributes"]["ui"]
    assert ui["widgets"][0]["dataSource"]["method"] == "stats"
    assert any(page["id"] == "models" for page in ui["pages"])


def test_index_selection_and_scores() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    models = index["models"]
    assert len(models) == 7
    by_id = {item["id"]: item for item in models}
    expected = {
        "relay-k2": (0.5706, "ours"),
        "relay-k12": (0.5417, "ours"),
        "relay-k4": (0.5397, "ours"),
        "relay-k8": (0.5199, "ours"),
        "bilstm": (0.4186, "baseline"),
        "resnet1d": (0.4178, "baseline"),
        "tlstm": (0.3522, "baseline"),
    }
    assert set(by_id) == set(expected)
    for model_id, (score, group) in expected.items():
        assert by_id[model_id]["score"] == score
        assert by_id[model_id]["class"] == group
    ours = [item["score"] for item in models if item["class"] == "ours"]
    baselines = [item["score"] for item in models if item["class"] == "baseline"]
    assert len(ours) == 4 and len(baselines) == 3
    assert min(ours) > max(baselines)
    assert [item["score"] for item in models] == sorted((item["score"] for item in models), reverse=True)

    adapter = _load_adapter()
    validated = adapter.validate_model_index(index)
    adapter.assert_ours_above_baselines(validated)
    for item in models:
        assert item["metric"] == "macro_f1"
        assert item["classes"] == ["N", "SVEB", "VEB", "F", "Q"]
        assert item["file"].endswith(".onnx")
        assert len(item["sha256"]) == 64


def test_feature_extraction_shape_and_zscore() -> None:
    adapter = _load_adapter()
    fs = 360
    samples = int(fs * 10)
    time = np.arange(samples) / fs
    signal = np.zeros((samples, 2), dtype=np.float32)
    signal[:, 0] = np.sin(2 * np.pi * 1.2 * time)
    signal[:, 1] = 0.5 * np.cos(2 * np.pi * 2.0 * time)
    peaks = list(range(90 + 36, samples - 144, 288))
    beats, positions = adapter.extract_beats(signal, peaks, fs)

    assert beats.shape[1:] == (2, adapter.WINDOW_SAMPLES)
    assert beats.dtype == np.float32
    assert positions.size == len(beats) == len(peaks)
    assert int(positions[0]) == peaks[0]
    assert float(np.abs(beats.mean(axis=2)).max()) < 1e-5
    std = beats.std(axis=2)
    assert np.all(std > 0.99) and np.all(std < 1.01)


def test_boundaries() -> None:
    adapter = _load_adapter()
    with pytest.raises(adapter.AdapterError) as info:
        adapter.validate_fs(250)
    assert info.value.code == "sampling_rate_mismatch"

    signal = np.zeros((500, 2), dtype=np.float32)
    with pytest.raises(adapter.AdapterError) as info:
        adapter.extract_beats(signal, [10], 360)
    assert info.value.code == "too_few_beats"

    with pytest.raises(adapter.AdapterError) as info:
        adapter.chunk_sequences(np.zeros((10, 2, 234), np.float32), list(range(10)))
    assert info.value.code == "too_few_beats"

    duplicated = adapter.normalize_channels(np.ones((500, 1), np.float32), 360)
    assert duplicated.shape == (500, 2)
    assert np.array_equal(duplicated[:, 0], duplicated[:, 1])


def test_softmax_and_aggregate() -> None:
    adapter = _load_adapter()
    logits = np.array([[1000.0, 0.0, 0.0, 0.0, 0.0], [0.0, 1000.0, 0.0, 0.0, 0.0]])
    probabilities = adapter.softmax(logits)
    assert np.all(np.isfinite(probabilities))
    assert np.allclose(probabilities.sum(axis=1), 1.0)

    summary = adapter.aggregate(probabilities)
    assert summary["counts"]["N"] == 1
    assert summary["counts"]["SVEB"] == 1
    assert summary["scoredBeats"] == 2
    assert summary["predictedClass"] == "N"
    assert summary["nonDiagnostic"]


def test_worker_list_models_and_unknown_model() -> None:
    responses = _run(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"apiVersion": "1.0"}},
            {"jsonrpc": "2.0", "id": 2, "method": "list_models", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "analyze", "params": {"modelId": "no-such"}},
            {"jsonrpc": "2.0", "id": 4, "method": "stats", "params": {}},
            {"jsonrpc": "2.0", "id": 5, "method": "deactivate", "params": {}},
        ]
    )
    by_id = {item["id"]: item for item in responses}
    assert by_id[1]["result"]["moduleId"] == "org.eclipsehealth.relay-ecg"
    assert len(by_id[2]["result"]["models"]) == 7
    assert by_id[2]["result"]["ordering"]["satisfied"] is True
    assert by_id[3]["error"]["data"]["reason"] == "model_not_found"
    assert by_id[3]["error"]["data"]["status"] == 404
    assert by_id[4]["result"]["latest"]["summaryText"] == "暂无分析"
    assert by_id[5]["result"]["ok"] is True


def test_missing_weights_returns_503(tmp_path: Path) -> None:
    responses = _run(
        [{"jsonrpc": "2.0", "id": 1, "method": "analyze", "params": {"modelId": "relay-k2"}}],
        weights_dir=str(tmp_path),
    )
    error = responses[0]["error"]
    assert error["data"]["reason"] == "model_missing"
    assert error["data"]["status"] == 503


@pytest.mark.skipif(
    not (WEIGHTS / "relay_k2.onnx").is_file(),
    reason="relay-ecg ONNX 未导出（运行 tools/export_onnx.py）",
)
def test_worker_analyzes_wfdb_sample() -> None:
    responses = _run(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "analyze",
                "params": {
                    "modelId": "relay-k2",
                    "wfdbPath": str(SAMPLE),
                    "options": {"maxSeconds": 120, "includeBeats": True},
                },
            }
        ]
    )
    result = responses[0]["result"]
    assert result["modelId"] == "relay-k2"
    assert result["leads"] == ["MLII", "V5"]
    assert result["nBeats"] >= 64
    assert result["nScoredBeats"] > 0
    summary = result["summary"]
    assert len(summary["probabilities"]) == 5
    assert abs(sum(summary["probabilities"]) - 1.0) < 1e-4
    assert sum(summary["counts"].values()) == result["nScoredBeats"]
    assert summary["predictedClass"] in summary["classes"]
    assert result["nonDiagnostic"]
    assert len(result["beats"]) <= 256

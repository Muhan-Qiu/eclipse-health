"""官方模块 org.eclipsehealth.relay-sleep 的 manifest、适配层、RPC 与权重测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "relay-sleep"
WEIGHTS_DIR = ROOT / "uploads" / "relay-sleep" / "models"
MAIN = MODULE_DIR / "src" / "main.py"
INDEX_PATH = MODULE_DIR / "models" / "index.json"
VERIFY_PATH = MODULE_DIR / "models" / "verify.json"
CLASSES = ["W", "N1", "N2", "N3", "R"]


def _load_adapter():
    spec = importlib.util.spec_from_file_location("relay_sleep_adapter", MODULE_DIR / "src" / "adapter.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(lines: list[dict], module_dir: Path | None = None) -> list[dict]:
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n"
    env = dict(os.environ)
    if module_dir is not None:
        env["ECLIPSE_MODULE_DIR"] = str(module_dir)
    proc = subprocess.run(
        [sys.executable, str(MAIN)],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=120,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]


def _index() -> list[dict]:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def test_manifest_matches_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["id"] == "org.eclipsehealth.relay-sleep"
    assert manifest["type"] == "analysis-model"
    assert manifest["permissions"] == ["records:read"]
    # numpy / onnxruntime 由核心运行时提供，模块不再声明依赖（见 docs/V4/BUGS.md BUG-001）。
    assert manifest["dependencies"] == []


def test_five_models_and_score_ordering() -> None:
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    models = manifest["contributes"]["models"]
    index = _index()
    verify = json.loads(VERIFY_PATH.read_text(encoding="utf-8"))
    assert len(models) == len(index) == len(verify["models"]) == 5
    assert {item["id"] for item in models} == {item["id"] for item in index}

    ours = [item["score"] for item in index if item["class"] == "ours"]
    baselines = [item["score"] for item in index if item["class"] == "baseline"]
    assert len(ours) == 3 and len(baselines) == 2
    assert min(ours) > max(baselines)
    assert all(item["metric"] == "balanced_accuracy" for item in index)
    assert all(item["classes"] == CLASSES for item in index)

    manifest_files = {item["id"]: item["files"][0] for item in models}
    for entry in index:
        assert manifest_files[entry["id"]]["sha256"] == entry["sha256"]
        assert manifest_files[entry["id"]]["path"] == f"models/{entry['file']}"
        assert entry["file"].endswith(".onnx")
        assert f"BA {entry['score']:.4f}" in next(
            model["name"] for model in models if model["id"] == entry["id"]
        )


def test_relay_features_shape_and_dt() -> None:
    adapter = _load_adapter()
    features = adapter.validate_features(np.zeros((10, 272), dtype=np.float32))
    assert features.shape == (1, 10, 272)
    batch = adapter.validate_features(np.ones((3, 10, 272), dtype=np.float32))
    assert batch.shape == (3, 10, 272)
    dt = adapter.validate_dt(None, 3)
    assert dt.shape == (3, 10, 1)
    assert np.all(dt == 1.0)
    assert adapter.validate_dt(np.ones(10), 1).shape == (1, 10, 1)
    assert adapter.validate_dt(np.ones((2, 10)), 2).shape == (2, 10, 1)

    bad_inputs = [
        np.zeros((9, 272)),
        np.zeros((10, 271)),
        np.zeros((10,)),
        np.full((10, 272), np.nan),
        np.array([["x"] * 272] * 10),
    ]
    for bad in bad_inputs:
        with pytest.raises(adapter.AdapterError):
            adapter.validate_features(bad)
    with pytest.raises(adapter.AdapterError):
        adapter.validate_dt(np.zeros((2, 10, 1)), 2)
    with pytest.raises(adapter.AdapterError):
        adapter.validate_dt(np.ones((2, 10, 1)), 3)


def test_baseline_windows_shape() -> None:
    adapter = _load_adapter()
    assert adapter.validate_windows(np.zeros((3, 2, 3000)), 2).shape == (1, 3, 2, 3000)
    assert adapter.validate_windows(np.zeros((2, 3, 1, 3000)), 1).shape == (2, 3, 1, 3000)
    with pytest.raises(adapter.AdapterError):
        adapter.validate_windows(np.zeros((3, 1, 3000)), 2)
    with pytest.raises(adapter.AdapterError):
        adapter.validate_windows(np.zeros((3, 2, 2999)), 2)


def test_softmax_and_summary() -> None:
    adapter = _load_adapter()
    logits = np.array([[0.0, 1.0, 2.0, 3.0, 4.0], [5.0, 5.0, 5.0, 5.0, 5.0]])
    probabilities = adapter.softmax(logits)
    assert np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-9)
    assert np.all(probabilities >= 0.0)
    assert probabilities[0].argmax() == 4

    windows = np.zeros((2, 10, 5))
    windows[:, :, 2] = 5.0
    summary = adapter.summarize(windows, "window")
    assert summary["total"] == 20
    assert summary["majority"] == "N2"
    assert summary["counts"]["N2"] == 20
    assert len(summary["perWindow"]) == 20
    sequence = adapter.summarize(np.eye(5), "sequence")
    assert sequence["majority"] == "W"
    assert len(sequence["perSequence"]) == 5


def test_missing_weights_are_reported_without_crash() -> None:
    available = any((MODULE_DIR / "models" / entry["file"]).is_file() for entry in _index())
    responses = _run(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"apiVersion": "1.0"}},
            {"jsonrpc": "2.0", "id": 2, "method": "health", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "list_models", "params": {}},
            {"jsonrpc": "2.0", "id": 4, "method": "stats", "params": {}},
            {"jsonrpc": "2.0", "id": 5, "method": "predict", "params": {"modelId": "nope"}},
            {"jsonrpc": "2.0", "id": 6, "method": "deactivate", "params": {}},
        ]
    )
    by_id = {item["id"]: item for item in responses}
    assert by_id[1]["result"]["moduleId"] == "org.eclipsehealth.relay-sleep"
    assert by_id[2]["result"]["ok"] is True
    assert by_id[3]["result"]["count"] == 5
    assert by_id[4]["result"]["hasData"] is False
    assert by_id[5]["error"]["data"]["reason"] == "unknown_model"
    assert by_id[6]["result"]["ok"] is True
    if not available:
        payload = _run(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "predict",
                    "params": {"modelId": "paper-highway-h-k2-c256", "features": np.zeros((10, 272)).tolist()},
                }
            ]
        )[0]
        assert payload["result"]["error"]["code"] == "model_unavailable"


def _stage_module(tmp_path: Path) -> Path | None:
    """把模块源码/索引和 uploads 权重放进临时目录，用于真实推理测试。"""
    if not WEIGHTS_DIR.is_dir() or not any(WEIGHTS_DIR.glob("*.onnx")):
        return None
    staging = tmp_path / "relay-sleep"
    shutil.copytree(MODULE_DIR / "src", staging / "src")
    shutil.copytree(MODULE_DIR / "models", staging / "models")
    for weight in WEIGHTS_DIR.glob("*.onnx"):
        target = staging / "models" / weight.name
        try:
            os.link(weight, target)
        except OSError:
            shutil.copy2(weight, target)
    return staging


def test_predict_with_real_weights(tmp_path: Path) -> None:
    staging = _stage_module(tmp_path)
    if staging is None:
        pytest.skip("uploads/relay-sleep/models 中没有 ONNX 权重")
    features = (np.arange(10 * 272, dtype=np.float32).reshape(10, 272) / 1000.0).tolist()
    responses = _run(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "predict",
                "params": {"modelId": "paper-highway-h-k2-c256", "features": features},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "predict",
                "params": {"modelId": "chambon2018-seed4", "windows": np.zeros((3, 2, 3000)).tolist()},
            },
        ],
        module_dir=staging,
    )
    by_id = {item["id"]: item for item in responses}
    relay = by_id[1]["result"]
    assert relay["shape"] == [1, 10, 5]
    assert len(relay["argmax"][0]) == 10
    assert relay["summary"]["total"] == 10
    probabilities = _load_adapter().softmax(relay["logits"])
    assert np.allclose(probabilities.sum(axis=-1), 1.0, atol=1e-5)

    baseline = by_id[2]["result"]
    assert baseline["shape"] == [1, 5]
    assert baseline["summary"]["total"] == 1

    npz_path = tmp_path / "features.npz"
    np.savez(npz_path, features=np.zeros((10, 272), dtype=np.float32))
    from_npz = _run(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "predict",
                "params": {"modelId": "paper-highway-h-k2-c256", "npzPath": str(npz_path)},
            }
        ],
        module_dir=staging,
    )[0]["result"]
    assert from_npz["shape"] == [1, 10, 5]

"""分析服务测试的共用工具（不依赖 pytest 夹具）。"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from eclipse_health_backend.analysis.ids import new_id, rfc3339

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
CARDIA_DIR = REPO_ROOT / "modules" / "official" / "cardia"
SAMPLES_DIR = BACKEND_ROOT / "resources" / "samples"


def fake_result(
    signal: Any,
    options: Any,
    *,
    n_beats: int = 80,
    fs: float | None = None,
) -> dict[str, Any]:
    """与 analysis.analyze 同形状的最小结果，用于不加载 ONNX 的链路测试。"""
    fs = float(fs or getattr(signal, "fs", 360.0))
    now = datetime.now(UTC)
    classes = ("N", "SVEB", "VEB", "F")
    beats: list[dict[str, Any]] = []
    for index in range(n_beats):
        probabilities = {"N": 0.94, "SVEB": 0.02, "VEB": 0.03, "F": 0.01}
        beats.append(
            {
                "index": index,
                "rPeakSample": int(index * fs + 100),
                "label": classes[index % 4],
                "confidence": 0.94,
                "rrPrevMs": 833,
                "probabilities": probabilities,
            }
        )
    measurements = [
        {
            "schema": "org.eclipsehealth.measurement/1",
            "id": new_id("msr"),
            "recordId": options.record_id,
            "analysisId": options.analysis_id,
            "code": "heart_rate_mean",
            "label": "平均心率",
            "value": 72.0,
            "unit": "bpm",
            "ucum": "/min",
            "range": {"startSec": 0, "endSec": 180},
            "confidence": 0.98,
            "method": "cardia-2.0",
            "warnings": [],
        },
        {
            "schema": "org.eclipsehealth.measurement/1",
            "id": new_id("msr"),
            "recordId": options.record_id,
            "analysisId": options.analysis_id,
            "code": "n_ratio",
            "label": "N 类占比",
            "value": 94.0,
            "unit": "%",
            "ucum": "",
            "range": {"startSec": 0, "endSec": 180},
            "confidence": 0.9,
            "method": "cardia-2.0",
            "warnings": [],
        },
    ]
    return {
        "schema": "org.eclipsehealth.analysis/1",
        "id": options.analysis_id,
        "recordId": options.record_id,
        "moduleId": "org.eclipsehealth.cardia",
        "modelId": "cardia-2.0",
        "modelVersion": "2.0.0",
        "task": "beat-classification",
        "status": "completed",
        "startedAt": rfc3339(now),
        "completedAt": rfc3339(now),
        "durationMs": 12,
        "summary": "平均心率 72 bpm · N 94.0% · SVEB 2.0% · VEB 3.0% · F 1.0%",
        "quality": {"score": 0.93, "level": "good", "warnings": [], "metrics": {}},
        "measurements": measurements,
        "beats": beats,
        "beatsRef": None,
        "annotations": [],
        "warnings": [],
        "parameters": {"engine": "cardia", "nBeatsClassified": n_beats},
        "provenance": {"preprocess": "cardia-v2", "preprocessVersion": "2.0"},
    }


def create_ecg_record(
    client: Any,
    member_id: str,
    samples: np.ndarray,
    *,
    fs: float = 360.0,
    lead: str = "MLII",
) -> dict[str, Any]:
    """把波形写进 imports/，再用记录 API 建一条带信号的记录。"""
    from eclipse_health_backend.settings import get_settings

    imports_dir = get_settings().imports_dir
    imports_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.f32"
    (imports_dir / name).write_bytes(np.asarray(samples, dtype="<f4").tobytes())
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T08:00:00Z",
        "timezone": "Asia/Shanghai",
        "source": {"kind": "file"},
        "samplingRate": fs,
        "leads": [lead],
        "unit": "mV",
        "signal": {"lead": lead, "fs": fs, "fileRef": name},
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_sine(n: int = 3600, fs: float = 360.0, freq: float = 1.2) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / fs
    return np.asarray(0.5 * np.sin(2 * np.pi * freq * t), dtype="<f4")


def wait_for_analysis(client: Any, analysis_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/analyses/{analysis_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"analysis {analysis_id} did not finish: {last}")


def load_sample_100() -> tuple[np.ndarray, float, str]:
    """MIT-BIH 100：返回 (mV float32 样本, fs, lead)。"""
    from eclipse_health_backend.analysis.ingest import load_wfdb

    signal = load_wfdb(SAMPLES_DIR / "100")
    return np.asarray(signal.samples, dtype="<f4"), float(signal.fs), signal.lead


def module_manifest() -> dict[str, Any]:
    return json.loads((CARDIA_DIR / "module.json").read_text(encoding="utf-8"))

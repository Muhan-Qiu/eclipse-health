"""报告测试工具：合成 ECG + 已完成分析，不依赖真实 ONNX。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from eclipse_health_backend.analysis.ids import new_id, rfc3339
from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.settings import get_settings

FS = 360.0
PERIOD_SEC = 0.85


def synthetic_ecg(seconds: float = 15.0, fs: float = FS) -> np.ndarray:
    """带 QRS/T 波与轻微噪声的合成波形；测试数据，不含真实健康信息。"""
    rng = np.random.default_rng(7)
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    ecg = 0.04 * np.sin(2 * np.pi * 0.28 * t) + rng.normal(0.0, 0.006, t.size)
    for start in np.arange(0.5, seconds, PERIOD_SEC):
        ecg += 1.1 * np.exp(-0.5 * ((t - start) / 0.011) ** 2)
        ecg -= 0.18 * np.exp(-0.5 * ((t - (start - 0.035)) / 0.018) ** 2)
        ecg += 0.22 * np.exp(-0.5 * ((t - (start + 0.24)) / 0.045) ** 2)
    return np.asarray(ecg, dtype="<f4")


def create_record(
    client: Any,
    member_id: str,
    *,
    notes: str = "晨起心悸，休息后缓解",
    seconds: float = 15.0,
) -> dict[str, Any]:
    imports_dir = get_settings().imports_dir
    imports_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.f32"
    (imports_dir / name).write_bytes(synthetic_ecg(seconds).tobytes())
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T08:00:00Z",
        "timezone": "Asia/Shanghai",
        "source": {
            "kind": "wearable",
            "manufacturer": "Synthetic",
            "device": "Test Watch",
        },
        "samplingRate": FS,
        "leads": ["MLII"],
        "unit": "mV",
        "tags": ["synthetic"],
        "notes": notes,
        "signal": {"lead": "MLII", "fs": FS, "fileRef": name},
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def analysis_result(record_id: str, analysis_id: str) -> dict[str, Any]:
    now = rfc3339(datetime.now(UTC))
    labels = ["N"] * 14
    labels[5] = "VEB"
    labels[9] = "SVEB"
    beats = []
    for index, label in enumerate(labels):
        beats.append(
            {
                "index": index,
                "rPeakSample": round((0.5 + index * PERIOD_SEC) * FS),
                "label": label,
                "confidence": 0.95,
                "rrPrevMs": int(PERIOD_SEC * 1000),
                "probabilities": {"N": 0.9, "SVEB": 0.03, "VEB": 0.05, "F": 0.02},
            }
        )

    def measurement(
        code: str,
        label: str,
        value: float | None,
        unit: str,
        ucum: str,
        method: str = "rr-intervals",
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": "org.eclipsehealth.measurement/1",
            "id": new_id("measurement"),
            "recordId": record_id,
            "analysisId": analysis_id,
            "code": code,
            "label": label,
            "value": value,
            "unit": unit,
            "ucum": ucum,
            "range": {"startSec": 0.0, "endSec": 15.0},
            "confidence": 0.93,
            "method": method,
            "warnings": warnings or [],
        }

    delineation = [{"code": "delineation_not_implemented", "message": "未实现波形 delineation"}]
    measurements = [
        measurement("heart_rate_mean", "平均心率", 72.4, "bpm", "/min"),
        measurement("heart_rate_min", "最小心率", 54.9, "bpm", "/min"),
        measurement("heart_rate_max", "最大心率", 114.9, "bpm", "/min"),
        measurement("rr_mean", "平均 RR 间期", 829.0, "ms", "ms"),
        measurement("sdnn", "SDNN", 48.7, "ms", "ms"),
        measurement("rmssd", "RMSSD", 62.9, "ms", "ms"),
        measurement("pnn50", "pNN50", 10.2, "%", "%"),
        measurement("qrs_duration", "QRS 时限", None, "ms", "ms", "unavailable", delineation),
        measurement("pr_interval", "PR 间期", None, "ms", "ms", "unavailable", delineation),
        measurement("qt_interval", "QT 间期", None, "ms", "ms", "unavailable", delineation),
        measurement("qtc", "QTc", None, "ms", "ms", "unavailable", delineation),
        measurement("n_ratio", "正常心搏比例", 85.71, "%", "%", "cardia-2.0"),
        measurement("svb_ratio", "室上性异位比例", 7.14, "%", "%", "cardia-2.0"),
        measurement("veb_ratio", "室性异位比例", 7.14, "%", "%", "cardia-2.0"),
        measurement("f_ratio", "融合搏动比例", 0.0, "%", "%", "cardia-2.0"),
    ]
    return {
        "schema": "org.eclipsehealth.analysis/1",
        "id": analysis_id,
        "recordId": record_id,
        "moduleId": "org.eclipsehealth.cardia",
        "modelId": "cardia-2.0",
        "modelVersion": "2.0.0",
        "task": "beat-classification",
        "status": "completed",
        "startedAt": now,
        "completedAt": now,
        "durationMs": 1200,
        "summary": "平均心率 72 bpm · N 85.7% · SVEB 7.1% · VEB 7.1% · F 0.0%",
        "quality": {"score": 0.93, "level": "good", "warnings": [], "segments": []},
        "measurements": measurements,
        "beats": beats,
        "beatsRef": None,
        "annotations": [],
        "warnings": [
            {
                "code": "research_use_only",
                "severity": "info",
                "message": "研究/教育用途，不构成医疗诊断",
                "startSec": None,
                "endSec": None,
            }
        ],
        "parameters": {
            "engine": "cardia",
            "sequenceLength": 64,
            "windowSamples": 180,
            "features": "cardia-104d",
        },
        "provenance": {
            "preprocess": "cardia-v2",
            "preprocessVersion": "2.0",
            "modelFile": "cardia_k4_best.onnx",
        },
    }


def create_record_without_signal(client: Any, member_id: str) -> dict[str, Any]:
    """只有元数据、没有波形的记录；用于验证报告的无波形分支。"""
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T09:00:00Z",
        "timezone": "Asia/Shanghai",
        "source": {"kind": "manual"},
        "samplingRate": FS,
        "leads": ["MLII"],
        "unit": "mV",
        "durationSec": 15.0,
        "tags": ["synthetic"],
        "notes": "",
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def add_completed_analysis(record_id: str) -> str:
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id="org.eclipsehealth.cardia",
            model_id="cardia-2.0",
            model_version="2.0.0",
        )
        analysis_repo.save_result(session, row, analysis_result(record_id, row.id))
        return row.id


def create_record_with_analysis(
    client: Any, member_id: str, *, notes: str = "晨起心悸，休息后缓解"
) -> tuple[dict[str, Any], str]:
    record = create_record(client, member_id, notes=notes)
    return record, add_completed_analysis(record["id"])


__all__ = [
    "FS",
    "add_completed_analysis",
    "analysis_result",
    "create_record",
    "create_record_with_analysis",
    "create_record_without_signal",
    "synthetic_ecg",
]

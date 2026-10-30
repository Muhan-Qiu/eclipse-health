"""导出/隐私测试工具：合成波形 + 完成分析 + 假报告文件，不依赖真实 ONNX。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from eclipse_health_backend.analysis.ids import rfc3339
from eclipse_health_backend.db import analysis_repo, report_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.settings import get_settings
from eclipse_health_backend.storage.files import write_report

FS = 360.0


def synthetic_ecg(seconds: float = 8.0, fs: float = FS) -> np.ndarray:
    rng = np.random.default_rng(11)
    samples = int(seconds * fs)
    t = np.arange(samples, dtype=np.float64) / fs
    ecg = 0.03 * np.sin(2 * np.pi * 0.25 * t) + rng.normal(0.0, 0.005, samples)
    for start in np.arange(0.5, seconds, 0.8):
        ecg += 1.0 * np.exp(-0.5 * ((t - start) / 0.012) ** 2)
    return np.asarray(ecg, dtype="<f4")


def create_record(
    client: Any,
    member_id: str,
    *,
    notes: str = "测试备注：晨起心悸",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    imports_dir = get_settings().imports_dir
    imports_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.f32"
    (imports_dir / name).write_bytes(synthetic_ecg().tobytes())
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
        "payload": payload or {},
        "signal": {"lead": "MLII", "fs": FS, "fileRef": name},
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _measurement(
    record_id: str, analysis_id: str, code: str, value: float, unit: str
) -> dict[str, Any]:
    return {
        "schema": "org.eclipsehealth.measurement/1",
        "id": new_id("measurement"),
        "recordId": record_id,
        "analysisId": analysis_id,
        "code": code,
        "label": code,
        "value": value,
        "unit": unit,
        "ucum": unit,
        "confidence": 0.9,
        "method": "test",
        "warnings": [],
    }


def analysis_result(record_id: str, analysis_id: str) -> dict[str, Any]:
    now = rfc3339(datetime.now(UTC))
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
        "durationMs": 900,
        "summary": "测试摘要",
        "quality": {"score": 0.9, "level": "good", "warnings": [], "segments": []},
        "measurements": [
            _measurement(record_id, analysis_id, "heart_rate_mean", 72.0, "bpm"),
            _measurement(record_id, analysis_id, "rmssd", 41.0, "ms"),
            _measurement(record_id, analysis_id, "n_ratio", 98.0, "%"),
        ],
        "beats": [
            {"index": 0, "rPeakSample": 400, "label": "N", "confidence": 0.95},
            {"index": 1, "rPeakSample": 700, "label": "N", "confidence": 0.91},
        ],
        "beatsRef": None,
        "annotations": [],
        "warnings": [],
        "parameters": {"engine": "cardia"},
        "provenance": {"preprocess": "cardia-v2"},
    }


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


def add_report(record_id: str, analysis_id: str) -> str:
    report_id = new_id("report")
    data = b"\x89PNG\r\n\x1a\n" + b"synthetic report body" * 16
    relative_path, sha256, size = write_report(report_id, "png", data)
    with session_scope() as session:
        report_repo.create_report_row(
            session,
            report_id=report_id,
            record_id=record_id,
            analysis_id=analysis_id,
            format="png",
            template="detailed",
            relative_path=relative_path,
            sha256=sha256,
            size=size,
            redacted=True,
        )
    return report_id


def create_record_with_analysis(
    client: Any, member_id: str, **kwargs: Any
) -> tuple[dict[str, Any], str]:
    record = create_record(client, member_id, **kwargs)
    return record, add_completed_analysis(record["id"])


def create_full_record(client: Any, member_id: str, **kwargs: Any) -> dict[str, Any]:
    record, analysis_id = create_record_with_analysis(client, member_id, **kwargs)
    report_id = add_report(record["id"], analysis_id)
    return {"record": record, "analysisId": analysis_id, "reportId": report_id}


__all__ = [
    "FS",
    "add_completed_analysis",
    "add_report",
    "analysis_result",
    "create_full_record",
    "create_record",
    "create_record_with_analysis",
    "synthetic_ecg",
]

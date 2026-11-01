"""助手测试的共用工具：合成记录、伪造已完成分析、解析 SSE。

只使用合成数据，不读取 ``uploads/`` 或真实样本。
"""

from __future__ import annotations

import json
from typing import Any

from eclipse_health_backend.analysis.ids import rfc3339
from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.domain.common import utc_now

MOCK_PROVIDER_ID = "llm_mock_test"


def create_record(
    client: Any,
    member_id: str,
    *,
    notes: str = "",
    captured_at: str = "2026-10-28T08:00:00Z",
    duration_sec: float = 180.0,
) -> dict[str, Any]:
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": captured_at,
        "timezone": "Asia/Shanghai",
        "source": {"kind": "file", "manufacturer": "Synthetic"},
        "samplingRate": 360.0,
        "leads": ["MLII"],
        "durationSec": duration_sec,
        "unit": "mV",
        "tags": ["synthetic"],
        "notes": notes,
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def measurements() -> list[dict[str, Any]]:
    base = [
        ("heart_rate_mean", "平均心率", 72.0, "bpm", "/min"),
        ("rmssd", "RMSSD", 41.5, "ms", "ms"),
        ("sdnn", "SDNN", 53.2, "ms", "ms"),
        ("n_ratio", "正常心搏比例", 98.3, "%", "%"),
        ("svb_ratio", "室上性异位比例", 1.2, "%", "%"),
        ("veb_ratio", "室性异位比例", 0.4, "%", "%"),
        ("f_ratio", "融合搏动比例", 0.1, "%", "%"),
    ]
    return [
        {
            "schema": "org.eclipsehealth.measurement/1",
            "code": code,
            "label": label,
            "value": value,
            "unit": unit,
            "ucum": ucum,
            "range": {"startSec": 0, "endSec": 180},
            "confidence": 0.95,
            "method": "cardia-2.0",
            "warnings": [],
        }
        for code, label, value, unit, ucum in base
    ]


def seed_analysis(record_id: str, *, summary: str | None = None) -> str:
    """直接写一条 completed 分析（不加载 ONNX）。"""
    now = rfc3339(utc_now())
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record_id,
            engine="cardia",
            module_id="org.eclipsehealth.cardia",
            model_id="cardia-2.0",
            model_version="2.0.0",
        )
        result = {
            "schema": "org.eclipsehealth.analysis/1",
            "id": row.id,
            "recordId": record_id,
            "moduleId": "org.eclipsehealth.cardia",
            "modelId": "cardia-2.0",
            "modelVersion": "2.0.0",
            "task": "beat-classification",
            "status": "completed",
            "startedAt": now,
            "completedAt": now,
            "durationMs": 12,
            "summary": summary or "平均心率 72 bpm · N 98.3% · SVEB 1.2% · VEB 0.4% · F 0.1%",
            "quality": {"score": 0.93, "level": "good", "warnings": [], "segments": []},
            "measurements": measurements(),
            "beats": [],
            "beatsRef": None,
            "annotations": [],
            "warnings": [],
            "parameters": {"engine": "cardia"},
            "provenance": {"preprocess": "cardia-v2"},
        }
        analysis_repo.save_result(session, row, result)
        return row.id


def parse_sse(lines: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """把 SSE 文本行解析成 ``[(event, data), ...]``。"""
    events: list[tuple[str, dict[str, Any]]] = []
    name: str | None = None
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].strip())
        elif line == "" and name is not None:
            payload = json.loads("\n".join(data)) if data else {}
            events.append((name, payload))
            name = None
            data = []
    if name is not None:
        payload = json.loads("\n".join(data)) if data else {}
        events.append((name, payload))
    return events


def stream_message(
    client: Any, session_id: str, body: dict[str, Any]
) -> tuple[int, list[tuple[str, dict[str, Any]]]]:
    with client.stream(
        "POST", f"/api/v1/assistant/sessions/{session_id}/messages", json=body
    ) as response:
        status = response.status_code
        if status != 200:
            return status, []
        return status, parse_sse(list(response.iter_lines()))

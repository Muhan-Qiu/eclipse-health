"""API 测试共用的小工具：合成正弦波，不含任何真实健康数据。"""

from __future__ import annotations

import numpy as np


def make_record_body(member_id: str, **overrides) -> dict:
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T08:00:00Z",
        "timezone": "Asia/Shanghai",
        "source": {"kind": "wearable", "manufacturer": "Synthetic"},
        "samplingRate": 500.0,
        "leads": ["I"],
        "unit": "mV",
        "tags": ["synthetic"],
        "notes": "",
    }
    body.update(overrides)
    return body


def sine_samples(n: int = 500, fs: float = 500.0, freq: float = 5.0) -> np.ndarray:
    t = np.arange(n, dtype="<f8") / fs
    return np.asarray(0.5 * np.sin(2 * np.pi * freq * t), dtype="<f4")


def create_record(client, member_id: str, **overrides) -> dict:
    response = client.post("/api/v1/records", json=make_record_body(member_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()

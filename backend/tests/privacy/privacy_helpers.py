"""隐私测试工具：内联小波形，避免依赖上传目录。"""

from __future__ import annotations

from typing import Any

import numpy as np

FS = 360.0


def create_record(
    client: Any,
    member_id: str,
    *,
    notes: str = "隐私测试备注",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    samples = [float(value) for value in np.zeros(360, dtype="<f4")]
    body = {
        "memberId": member_id,
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T08:00:00Z",
        "timezone": "Asia/Shanghai",
        "source": {"kind": "manual"},
        "samplingRate": FS,
        "leads": ["MLII"],
        "unit": "mV",
        "tags": ["test"],
        "notes": notes,
        "payload": payload or {},
        "signal": {"lead": "MLII", "fs": FS, "samples": samples},
    }
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


__all__ = ["FS", "create_record"]

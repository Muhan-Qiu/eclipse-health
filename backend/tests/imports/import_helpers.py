"""导入测试的小工具；文件名独立，避免与 ``tests/api/helpers.py`` 冲突。"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np

API = "/api/v1"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = BACKEND_ROOT / "resources" / "samples"


def csv_text(
    values,
    *,
    header: str | None = None,
    separator: str = ",",
    time_step: float | None = None,
) -> str:
    lines: list[str] = []
    if header:
        lines.append(header)
    for index, value in enumerate(values):
        if time_step is None:
            lines.append(f"{value}")
        else:
            lines.append(f"{index * time_step:.9g}{separator}{value}")
    return "\n".join(lines) + "\n"


def upload_preview(client, name: str, text: str | bytes, **form):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return client.post(
        f"{API}/imports/preview",
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


def path_preview(client, path: Path | str, **form):
    return client.post(f"{API}/imports/preview", data={"path": str(path), **form})


def commit_body(member_id: str, **parameters) -> dict:
    return {
        "memberId": member_id,
        "capturedAt": "2026-10-28T10:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "tags": ["导入"],
        "notes": "",
        "parameters": parameters,
    }


def commit(client, import_id: str, member_id: str, **parameters):
    return client.post(
        f"{API}/imports/{import_id}/commit", json=commit_body(member_id, **parameters)
    )


def read_signal(client, record_id: str, lead: str | None = None) -> np.ndarray:
    params = {"lead": lead} if lead else {}
    response = client.get(f"{API}/records/{record_id}/signal", params=params)
    assert response.status_code == 200, response.text
    return np.frombuffer(response.content, dtype="<f4")


def sha256_tag(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def zip_samples(record: str = "100", *, arc_prefix: str = "") -> bytes:
    """把 MIT-BIH 样本打包成 ZIP 字节，供 multipart 上传。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for suffix in (".hea", ".dat", ".atr"):
            source = SAMPLES_DIR / f"{record}{suffix}"
            if not source.exists():
                continue
            archive.write(source, f"{arc_prefix}{record}{suffix}")
    return buffer.getvalue()


def expected_mv(record: str, channel: int = 0) -> np.ndarray:
    """按 WFDB 公式 (d - baseline) / gain 计算参考波形（mV）。"""
    import wfdb

    digital = wfdb.rdrecord(str(SAMPLES_DIR / record), physical=False)
    return (
        digital.d_signal[:, channel] - digital.baseline[channel]
    ) / digital.adc_gain[channel]


__all__ = [
    "API",
    "BACKEND_ROOT",
    "SAMPLES_DIR",
    "commit",
    "commit_body",
    "csv_text",
    "expected_mv",
    "path_preview",
    "read_signal",
    "sha256_tag",
    "upload_preview",
    "zip_samples",
]

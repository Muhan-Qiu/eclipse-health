from __future__ import annotations

from pathlib import Path

import numpy as np
from helpers import make_record_body, sine_samples

from eclipse_health_backend.settings import get_settings


def _create_with_signal(client, member_id: str, samples: np.ndarray) -> dict:
    body = make_record_body(member_id)
    body["signal"] = {"lead": "I", "fs": 500.0, "samples": samples.tolist()}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_signal_roundtrip_is_bit_exact(client, default_member: dict) -> None:
    samples = sine_samples(n=1500)
    record = _create_with_signal(client, default_member["id"], samples)

    response = client.get(f"/api/v1/records/{record['id']}/signal", params={"lead": "I"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-signal-lead"] == "I"
    assert response.headers["x-signal-samples"] == "1500"
    assert response.headers["x-signal-fs"] == "500"
    assert response.headers["x-signal-unit"] == "mV"

    restored = np.frombuffer(response.content, dtype="<f4")
    assert np.array_equal(restored, samples)


def test_signal_without_lead_uses_only_signal(client, default_member: dict) -> None:
    samples = sine_samples(n=100)
    record = _create_with_signal(client, default_member["id"], samples)

    response = client.get(f"/api/v1/records/{record['id']}/signal")
    assert response.status_code == 200
    assert np.array_equal(np.frombuffer(response.content, dtype="<f4"), samples)


def test_signal_metadata_endpoint(client, default_member: dict) -> None:
    samples = sine_samples(n=250)
    record = _create_with_signal(client, default_member["id"], samples)

    response = client.get(f"/api/v1/records/{record['id']}/signals")
    assert response.status_code == 200
    signals = response.json()
    assert len(signals) == 1
    assert signals[0]["lead"] == "I"
    assert signals[0]["shape"] == [250]
    assert signals[0]["storage"]["relativePath"].startswith("signals/sig_")
    assert signals[0]["schema"] == "org.eclipsehealth.signal/1"


def test_signal_etag(client, default_member: dict) -> None:
    record = _create_with_signal(client, default_member["id"], sine_samples(n=64))
    first = client.get(f"/api/v1/records/{record['id']}/signal", params={"lead": "I"})
    etag = first.headers["etag"]

    second = client.get(
        f"/api/v1/records/{record['id']}/signal",
        params={"lead": "I"},
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.content == b""


def test_signal_unknown_lead(client, default_member: dict) -> None:
    record = _create_with_signal(client, default_member["id"], sine_samples(n=64))
    response = client.get(f"/api/v1/records/{record['id']}/signal", params={"lead": "V1"})
    assert response.status_code == 404
    assert response.json()["code"] == "signal_not_found"


def test_signal_file_ref(client, default_member: dict, data_dir: Path) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    samples = sine_samples(n=320)
    (settings.imports_dir / "from_file.f32").write_bytes(samples.tobytes())

    body = make_record_body(default_member["id"])
    body["signal"] = {"lead": "I", "fs": 500.0, "fileRef": "from_file.f32"}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 201, response.text
    record = response.json()

    wave = client.get(f"/api/v1/records/{record['id']}/signal", params={"lead": "I"})
    assert np.array_equal(np.frombuffer(wave.content, dtype="<f4"), samples)


def test_signal_file_ref_rejects_traversal(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"])
    body["signal"] = {"lead": "I", "fs": 500.0, "fileRef": "../../etc/passwd"}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file_ref"


def test_signal_file_ref_must_be_float32(client, default_member: dict) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    (settings.imports_dir / "odd.bin").write_bytes(b"\x01\x02\x03")

    body = make_record_body(default_member["id"])
    body["signal"] = {"lead": "I", "fs": 500.0, "fileRef": "odd.bin"}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_signal_file"


def test_signal_samples_required(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"])
    body["signal"] = {"lead": "I", "fs": 500.0, "samples": []}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "empty_signal"


def test_signal_sampling_rate_required(client, default_member: dict) -> None:
    body = make_record_body(default_member["id"])
    body.pop("samplingRate")
    body["signal"] = {"lead": "I", "samples": [0.0, 0.1]}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "sampling_rate_required"


def test_signal_inline_size_limit(client, default_member: dict, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "signal_inline_max_samples", 4)
    body = make_record_body(default_member["id"])
    body["signal"] = {"lead": "I", "samples": [0.0, 0.1, 0.2, 0.3, 0.4]}
    response = client.post("/api/v1/records", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "signal_too_many_samples"


def test_signal_tampering_is_detected(client, default_member: dict) -> None:
    record = _create_with_signal(client, default_member["id"], sine_samples(n=32))
    signal_id = record["signalIds"][0]
    path = get_settings().signals_dir / f"{signal_id}.f32"
    path.write_bytes(b"\x00" * 16)

    response = client.get(f"/api/v1/records/{record['id']}/signal", params={"lead": "I"})
    assert response.status_code == 500
    assert response.json()["code"] == "storage_integrity_error"


def test_signal_requires_existing_record(client) -> None:
    response = client.get(
        "/api/v1/records/rec_00000000-0000-0000-0000-000000000000/signal",
        params={"lead": "I"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "record_not_found"

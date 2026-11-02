"""分析运行控制：取消、强制重发、暂停/恢复、重试、删除记录时取消。

覆盖「ECG 逐搏分类卡在 40%，其它任务全部排队，删了也不能继续分析」的回归。
"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis_service_helpers import create_ecg_record, fake_result, make_sine, wait_for_analysis
from fastapi.testclient import TestClient

import eclipse_health_backend.analysis.engine as engine_module
import eclipse_health_backend.analysis_service.service as service_module


def _wait_status(
    client: TestClient, analysis_id: str, statuses: set[str], *, timeout: float = 10.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/analyses/{analysis_id}").json()
        if last.get("status") in statuses:
            return last
        time.sleep(0.02)
    raise AssertionError(f"analysis {analysis_id} never reached {statuses}: {last}")


def _patch_slow_analyze(monkeypatch: Any, gate: threading.Event) -> None:
    def slow(signal: Any, options: Any) -> dict[str, Any]:
        gate.wait(timeout=15)
        return fake_result(signal, options)

    monkeypatch.setattr(engine_module, "analyze", slow)
    # 取消后不必真等 2 秒宽限期，测试更快。
    monkeypatch.setattr(service_module, "CANCEL_GRACE_S", 0.15)


def test_cancel_running_releases_queue_and_next_job_completes(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: Any,
) -> None:
    gate = threading.Event()
    _patch_slow_analyze(monkeypatch, gate)
    record = create_ecg_record(client, default_member["id"], make_sine())

    first = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    _wait_status(client, first["analysisId"], {"running"})

    cancelled = client.post(f"/api/v1/analyses/{first['analysisId']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancelled"] is True

    detail = _wait_status(client, first["analysisId"], {"cancelled"})
    assert detail["progress"] is None
    assert detail["error"]["code"] == "cancelled"

    # 旧任务被取消后，同记录可以立即再次发起；队列不会被永久占住。
    gate.set()
    second = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    assert second["analysisId"] != first["analysisId"]
    completed = wait_for_analysis(client, second["analysisId"], timeout=15)
    assert completed["status"] == "completed"


def test_cancel_queued_job_never_starts(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: Any,
) -> None:
    gate = threading.Event()
    _patch_slow_analyze(monkeypatch, gate)
    first_record = create_ecg_record(client, default_member["id"], make_sine())
    second_record = create_ecg_record(client, default_member["id"], make_sine())

    first = client.post(f"/api/v1/records/{first_record['id']}/analyses", json={}).json()
    _wait_status(client, first["analysisId"], {"running"})
    second = client.post(f"/api/v1/records/{second_record['id']}/analyses", json={}).json()
    queued = _wait_status(client, second["analysisId"], {"queued", "running"})
    assert queued["status"] == "queued"

    response = client.post(f"/api/v1/analyses/{second['analysisId']}/cancel")
    assert response.status_code == 200
    detail = _wait_status(client, second["analysisId"], {"cancelled"})
    assert detail["error"]["code"] == "cancelled"

    gate.set()
    wait_for_analysis(client, first["analysisId"], timeout=15)


def test_force_submit_supersedes_stuck_analysis(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: Any,
) -> None:
    gate = threading.Event()
    _patch_slow_analyze(monkeypatch, gate)
    record = create_ecg_record(client, default_member["id"], make_sine())

    first = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    _wait_status(client, first["analysisId"], {"running"})

    force = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"force": True}
    )
    assert force.status_code == 202, force.text
    accepted = force.json()
    assert accepted["analysisId"] != first["analysisId"]
    _wait_status(client, first["analysisId"], {"cancelled"})

    gate.set()
    completed = wait_for_analysis(client, accepted["analysisId"], timeout=15)
    assert completed["status"] == "completed"


def test_pause_and_resume_queue(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    fake_analyze: Any,
) -> None:
    paused = client.post("/api/v1/analyses/queue/pause")
    assert paused.status_code == 200
    assert paused.json()["paused"] is True

    record = create_ecg_record(client, default_member["id"], make_sine())
    accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    time.sleep(0.25)
    assert client.get(f"/api/v1/analyses/{accepted['analysisId']}").json()["status"] == "queued"

    resumed = client.post("/api/v1/analyses/queue/resume")
    assert resumed.json()["paused"] is False
    detail = wait_for_analysis(client, accepted["analysisId"], timeout=15)
    assert detail["status"] == "completed"


def test_retry_failed_analysis_creates_new_job(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: Any,
) -> None:
    def failing(signal: Any, options: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(engine_module, "analyze", failing)
    record = create_ecg_record(client, default_member["id"], make_sine())
    first = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    failed = wait_for_analysis(client, first["analysisId"])
    assert failed["status"] == "failed"

    monkeypatch.setattr(
        engine_module, "analyze", lambda signal, options: fake_result(signal, options)
    )
    retried = client.post(f"/api/v1/analyses/{first['analysisId']}/retry")
    assert retried.status_code == 202, retried.text
    new_id = retried.json()["analysisId"]
    assert new_id != first["analysisId"]
    completed = wait_for_analysis(client, new_id, timeout=15)
    assert completed["status"] == "completed"


def test_delete_record_cancels_active_analysis(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: Any,
) -> None:
    gate = threading.Event()
    _patch_slow_analyze(monkeypatch, gate)
    record = create_ecg_record(client, default_member["id"], make_sine())
    accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    _wait_status(client, accepted["analysisId"], {"running"})

    assert client.delete(f"/api/v1/records/{record['id']}").status_code in {200, 204}
    detail = _wait_status(client, accepted["analysisId"], {"cancelled"})
    assert detail["error"]["code"] == "record_deleted"

    gate.set()


def test_queue_status_and_recover(client: TestClient, direct_service: Any) -> None:
    status = client.get("/api/v1/analyses/queue")
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["paused"] is False
    assert "engine" in payload
    assert payload["jobTimeoutSeconds"] > 0

    recovered = client.post("/api/v1/analyses/recover")
    assert recovered.status_code == 200
    assert "recovered" in recovered.json()

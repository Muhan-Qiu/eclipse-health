"""分析 API 主链路（直调模式 + 假引擎，不依赖 ONNX）。"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from analysis_service_helpers import create_ecg_record, fake_result, make_sine, wait_for_analysis
from fastapi.testclient import TestClient
from sqlmodel import select

from eclipse_health_backend.analysis.types import InsufficientBeatsError
from eclipse_health_backend.app import app
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.models import AnalysisTable, MeasurementTable


def test_full_flow_persists_result(
    client: TestClient, default_member: dict, direct_service: Any, fake_analyze: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine())

    created = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
    assert created.status_code == 202, created.text
    accepted = created.json()
    assert accepted["recordId"] == record["id"]
    assert accepted["engine"] == "cardia"
    assert accepted["status"] in {"queued", "running"}

    detail = wait_for_analysis(client, accepted["analysisId"])
    assert detail["status"] == "completed", detail
    assert detail["progress"] == {"stage": "summary", "percent": 100}
    assert detail["error"] is None
    assert detail["beatsTotal"] == 80
    assert len(detail["beats"]) == 80
    for beat in detail["beats"][:5]:
        assert set(beat["probabilities"]) == {"N", "SVEB", "VEB", "F"}
        assert abs(sum(beat["probabilities"].values()) - 1.0) < 1e-6
    assert [item["code"] for item in detail["measurements"]] == [
        "heart_rate_mean",
        "n_ratio",
    ]
    assert detail["measurements"][0]["unit"] == "bpm"

    with session_scope() as session:
        analysis_row = session.get(AnalysisTable, accepted["analysisId"])
        assert analysis_row is not None and analysis_row.status == "completed"
        measurements = session.exec(select(MeasurementTable)).all()
        assert len(measurements) == 2

    # includeBeats=false 不带逐搏，但给出总数
    without_beats = client.get(
        f"/api/v1/analyses/{accepted['analysisId']}", params={"includeBeats": "false"}
    ).json()
    assert without_beats["beats"] is None
    assert without_beats["beatsTotal"] == 80

    page = client.get(
        f"/api/v1/analyses/{accepted['analysisId']}/beats",
        params={"offset": 10, "limit": 5},
    ).json()
    assert page["total"] == 80
    assert page["offset"] == 10
    assert [beat["index"] for beat in page["items"]] == [10, 11, 12, 13, 14]

    listed = client.get(f"/api/v1/records/{record['id']}/analyses").json()
    assert [item["id"] for item in listed["items"]] == [accepted["analysisId"]]
    assert "beats" not in listed["items"][0]


def test_second_post_reuses_active_analysis(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = threading.Event()

    def slow(signal: Any, options: Any) -> dict:
        gate.wait(timeout=10)
        return fake_result(signal, options)

    import eclipse_health_backend.analysis.engine as engine_module

    monkeypatch.setattr(engine_module, "analyze", slow)
    record = create_ecg_record(client, default_member["id"], make_sine())

    first = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
    assert first.status_code == 202
    second = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
    assert second.status_code == 202
    assert second.json()["analysisId"] == first.json()["analysisId"]

    running = client.get(f"/api/v1/analyses/{first.json()['analysisId']}").json()
    assert running["status"] in {"queued", "running"}
    if running["progress"]:
        assert running["progress"]["stage"] in {"quality", "inference"}

    gate.set()
    detail = wait_for_analysis(client, first.json()["analysisId"])
    assert detail["status"] == "completed"

    # 完成后再发起 → 新任务
    third = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
    assert third.status_code == 202
    assert third.json()["analysisId"] != first.json()["analysisId"]


def test_too_few_beats_is_persisted_as_failed(
    client: TestClient,
    default_member: dict,
    direct_service: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(signal: Any, options: Any) -> dict:
        raise InsufficientBeatsError("有效心搏只有 3 个（<64）")

    import eclipse_health_backend.analysis.engine as engine_module

    monkeypatch.setattr(engine_module, "analyze", failing)
    record = create_ecg_record(client, default_member["id"], make_sine(n=720))

    accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    detail = wait_for_analysis(client, accepted["analysisId"])
    assert detail["status"] == "failed"
    assert detail["error"]["code"] == "too_few_beats"
    assert detail["beats"] == []


def test_record_without_signal_conflicts(client: TestClient, default_member: dict) -> None:
    body = {
        "memberId": default_member["id"],
        "recordType": "org.eclipsehealth.ecg",
        "capturedAt": "2026-10-28T08:00:00Z",
        "timezone": "Asia/Shanghai",
        "samplingRate": 360.0,
        "leads": ["MLII"],
    }
    record = client.post("/api/v1/records", json=body).json()

    response = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "record_has_no_signal"


def test_unknown_record_and_analysis_are_404(client: TestClient) -> None:
    response = client.post("/api/v1/records/rec_00000000-0000-7000-8000-000000000000/analyses", json={})
    assert response.status_code == 404
    assert response.json()["code"] == "record_not_found"
    assert client.get("/api/v1/analyses/ana_00000000-0000-7000-8000-000000000000").status_code == 404
    assert (
        client.get("/api/v1/analyses/ana_00000000-0000-7000-8000-000000000000/beats").status_code
        == 404
    )


def test_unknown_engine_is_rejected(
    client: TestClient, default_member: dict, direct_service: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine())
    response = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": "other"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_engine"


def test_result_survives_client_restart(
    client: TestClient, default_member: dict, direct_service: Any, fake_analyze: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine())
    accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
    detail = wait_for_analysis(client, accepted["analysisId"])
    assert detail["status"] == "completed"

    # 新的 app 生命周期 = 模拟重启：同一个数据目录下结果仍可查询。
    with TestClient(app) as restarted:
        response = restarted.get(f"/api/v1/analyses/{accepted['analysisId']}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert len(payload["beats"]) == 80
        assert payload["summary"] == detail["summary"]


def test_module_crash_marks_analysis_failed(
    client: TestClient,
    default_member: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eclipse_health_backend.analysis_service import AnalysisService, set_analysis_service
    from eclipse_health_backend.modules.errors import ModuleError

    class CrashBridge:
        def warmup(self) -> float:
            return 0.01

        def analyze(self, request: dict, *, timeout: float | None = None) -> dict:
            raise ModuleError("MODULE_CRASH", "模块进程已退出")

    service = AnalysisService(direct=False, start_warmup=False)
    service._bridge = CrashBridge()
    set_analysis_service(service)
    try:
        record = create_ecg_record(client, default_member["id"], make_sine())
        accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={}).json()
        detail = wait_for_analysis(client, accepted["analysisId"])
        assert detail["status"] == "failed"
        assert detail["error"]["code"] == "module_crash"
        assert detail["error"]["details"]["moduleCode"] == "MODULE_CRASH"
    finally:
        service.shutdown()
        set_analysis_service(None)


def test_stale_running_analysis_is_failed_on_start(
    client: TestClient, default_member: dict, direct_service: Any
) -> None:
    from eclipse_health_backend.analysis_service import AnalysisService
    from eclipse_health_backend.db import analysis_repo

    record = create_ecg_record(client, default_member["id"], make_sine())
    with session_scope() as session:
        row = analysis_repo.create_analysis(
            session,
            record_id=record["id"],
            engine="cardia",
            module_id="org.eclipsehealth.cardia",
            model_id="cardia-2.0",
            model_version="2.0.0",
        )
        analysis_repo.update_status(
            session, row, status="running", progress={"stage": "quality", "percent": 10}
        )
        stale_id = row.id

    AnalysisService(direct=True, start_warmup=False)  # 构造即做遗留任务回收

    detail = client.get(f"/api/v1/analyses/{stale_id}").json()
    assert detail["status"] == "failed"
    assert detail["error"]["code"] == "interrupted"
    assert detail["progress"] is None

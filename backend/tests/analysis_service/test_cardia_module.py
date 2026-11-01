"""Cardia 模块全链路（真实 ONNX）：安装 → 启动 → 预热 → analyze → 落库 → 重启查询。

模块自带 onnxsim 简化权重，会话初始化约 1.5 秒（原图约 150 秒）。原图对照
（简化图 vs 原图逐搏概率）在 ``tests/analysis/test_alignment.py`` 的 slow 测试里。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from analysis_service_helpers import create_ecg_record, load_sample_100, wait_for_analysis
from fastapi.testclient import TestClient
from sqlmodel import select

from eclipse_health_backend.analysis_service import AnalysisService, set_analysis_service
from eclipse_health_backend.app import app
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.models import MeasurementTable
from eclipse_health_backend.modules.api import get_manager, init_module_system
from eclipse_health_backend.settings import get_settings

pytestmark = pytest.mark.slow

CLASSES = {"N", "SVEB", "VEB", "F"}


def _wait_engine_ready(client: TestClient, timeout: float = 900.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get("/api/v1/engine").json()
        if body["status"] == "ready":
            return body
        if body["status"] == "error":
            raise AssertionError(f"engine warmup failed: {body}")
        time.sleep(0.5)
    raise AssertionError(f"engine not ready in {timeout}s: {body}")


def test_cardia_end_to_end(
    client: TestClient, default_member: dict, cardia_package: Path
) -> None:
    # client 夹具的 reset_db() 在建表之后执行，模块注册表需要重新创建。
    init_module_system()
    get_manager().install(cardia_package, enable=True)

    service = AnalysisService(auto_install=False, start_warmup=True, warm_timeout_s=900.0)
    set_analysis_service(service)
    try:
        warm_started = time.perf_counter()
        ready = _wait_engine_ready(client)
        warm_seconds = time.perf_counter() - warm_started
        assert ready["readyAt"]
        assert ready["moduleId"] == "org.eclipsehealth.cardia"
        assert ready["warmupSeconds"] is not None
        # 简化权重：会话初始化 ~1.3s。warmup 还含模块进程导入，受机器负载影响，
        # 但两者都必须挡住 150s 级回归（目标 ≤3s）。
        assert ready["warmupSeconds"] < 30.0, ready["warmupSeconds"]
        health = get_manager().call("org.eclipsehealth.cardia", "health", {})
        assert health["model"]["file"] == "cardia_k4_best_sim.onnx"
        assert health["model"]["variant"] == "onnx-simplified"
        assert health["model"]["sessionInitSeconds"] < 3.0

        samples, fs, lead = load_sample_100()
        record = create_ecg_record(client, default_member["id"], samples, fs=fs, lead=lead)

        started = time.perf_counter()
        accepted = client.post(f"/api/v1/records/{record['id']}/analyses", json={})
        assert accepted.status_code == 202, accepted.text
        analysis_id = accepted.json()["analysisId"]

        detail = wait_for_analysis(client, analysis_id, timeout=600.0)
        analyze_seconds = time.perf_counter() - started
        assert detail["status"] == "completed", detail.get("error")
        assert detail["beatsTotal"] > 1800
        assert len(detail["beats"]) == detail["beatsTotal"]
        labels = {beat["label"] for beat in detail["beats"]}
        assert labels <= CLASSES
        for beat in detail["beats"][:20]:
            assert abs(sum(beat["probabilities"].values()) - 1.0) < 1e-5
        codes = {item["code"] for item in detail["measurements"]}
        assert {"heart_rate_mean", "rr_mean", "sdnn", "rmssd", "n_ratio"} <= codes
        assert detail["quality"]["score"] is not None
        assert detail["durationMs"] and detail["durationMs"] > 0
        assert detail["provenance"]["modelFile"] == "cardia_k4_best_sim.onnx"

        with session_scope() as session:
            stored = session.exec(
                select(MeasurementTable).where(MeasurementTable.analysis_id == analysis_id)
            ).all()
            assert len(stored) == len(detail["measurements"])

        # 临时波形文件必须清理
        temp_dir = get_settings().data_dir / "tmp" / "analyses" / analysis_id
        assert not temp_dir.exists()

        # 短记录：<64 搏 → 落库为 failed + too_few_beats
        short_record = create_ecg_record(
            client, default_member["id"], samples[: int(fs * 5)], fs=fs, lead=lead
        )
        short_accepted = client.post(
            f"/api/v1/records/{short_record['id']}/analyses", json={}
        ).json()
        short_detail = wait_for_analysis(client, short_accepted["analysisId"], timeout=120.0)
        assert short_detail["status"] == "failed"
        assert short_detail["error"]["code"] == "too_few_beats", short_detail["error"]

        # 模拟重启：新 app 生命周期、同一数据目录，结果仍可查询
        with TestClient(app) as restarted:
            payload = restarted.get(f"/api/v1/analyses/{analysis_id}").json()
            assert payload["status"] == "completed"
            assert payload["beatsTotal"] == detail["beatsTotal"]
            assert payload["summary"] == detail["summary"]

        print(
            f"\n[cardia] model={health['model']['file']} "
            f"import={health['model']['importSeconds']}s "
            f"sessionInit={health['model']['sessionInitSeconds']}s "
            f"warmup={ready['warmupSeconds']}s wall={warm_seconds:.1f}s "
            f"postToCompleted={analyze_seconds:.2f}s durationMs={detail['durationMs']} "
            f"beats={detail['beatsTotal']} measurements={len(detail['measurements'])}"
        )
    finally:
        service.shutdown()
        set_analysis_service(None)

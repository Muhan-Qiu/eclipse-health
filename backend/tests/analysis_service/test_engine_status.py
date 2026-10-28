"""引擎状态机与模块桥接（不加载 ONNX）。"""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from eclipse_health_backend.analysis_service import (
    AnalysisService,
    CardiaBridge,
    set_analysis_service,
)
from eclipse_health_backend.modules.errors import ModuleError


class _StubBridge:
    def __init__(self, *, seconds: float = 0.2, error: str | None = None) -> None:
        self.seconds = seconds
        self.error = error
        self.calls = 0

    def warmup(self) -> float:
        self.calls += 1
        time.sleep(self.seconds)
        if self.error:
            raise ModuleError("MODEL_LOAD_FAILED", self.error)
        return self.seconds

    def model_card(self) -> dict[str, Any]:
        return {}


def _wait_status(client: TestClient, expected: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get("/api/v1/engine").json()
        if body["status"] == expected:
            return body
        time.sleep(0.02)
    raise AssertionError(f"engine never reached {expected}: {body}")


def test_engine_goes_warming_then_ready(client: TestClient) -> None:
    service = AnalysisService(direct=False, start_warmup=False)
    bridge = _StubBridge(seconds=0.2)
    service._bridge = bridge
    set_analysis_service(service)
    try:
        initial = client.get("/api/v1/engine").json()
        assert initial["status"] == "warming"
        assert initial["moduleId"] == "org.eclipsehealth.cardia"
        assert initial["modelId"] == "cardia-2.0"

        service.start()
        ready = _wait_status(client, "ready")
        assert ready["readyAt"]
        assert ready["warmupSeconds"] >= 0.19
        assert ready["error"] is None
        assert bridge.calls == 1
    finally:
        service.shutdown()
        set_analysis_service(None)


def test_engine_reports_warmup_failure(client: TestClient) -> None:
    service = AnalysisService(direct=False, start_warmup=False)
    service._bridge = _StubBridge(seconds=0.01, error="模型文件损坏")
    set_analysis_service(service)
    try:
        service.start()
        failed = _wait_status(client, "error")
        assert "模型文件损坏" in (failed["error"] or "")
        assert failed["message"].startswith("Cardia 模型预热失败")
    finally:
        service.shutdown()
        set_analysis_service(None)


class _FakeManager:
    """只实现 CardiaBridge 需要的四个方法。"""

    def __init__(self) -> None:
        self.installed = False
        self.install_calls = 0
        self.calls: list[str] = []
        self.health_polls = 0

    def get_module(self, module_id: str) -> dict[str, Any]:
        if not self.installed:
            raise ModuleError("MODULE_NOT_FOUND", "模块未安装")
        return {"id": module_id, "name": "Cardia 2.0", "version": "1.0.0"}

    def install(self, path: Any, *, enable: bool = False) -> dict[str, Any]:
        self.install_calls += 1
        self.installed = True
        return {"id": "org.eclipsehealth.cardia", "enabled": enable}

    def call(self, module_id: str, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(method)
        if method == "warmup":
            return {"warm": False}
        if method == "health":
            self.health_polls += 1
            if self.health_polls >= 2:
                return {"ok": True, "warm": True, "warmupSeconds": 150.5, "error": None}
            return {"ok": True, "warm": False, "warmupSeconds": None, "error": None}
        if method == "analyze":
            return {"status": "completed", "id": "ana_test"}
        raise AssertionError(f"unexpected rpc {method}")


def test_bridge_installs_from_source_and_polls_warmup() -> None:
    manager = _FakeManager()
    bridge = CardiaBridge(lambda: manager, auto_install=True, poll_interval_s=0.01)
    assert bridge.ensure_installed()["enabled"] is True
    assert manager.install_calls == 1

    seconds = bridge.warmup()
    assert seconds == 150.5
    assert manager.calls[:2] == ["warmup", "health"]
    assert manager.health_polls == 2


def test_bridge_without_auto_install_raises() -> None:
    manager = _FakeManager()
    bridge = CardiaBridge(lambda: manager, auto_install=False)
    try:
        bridge.ensure_installed()
    except ModuleError as exc:
        assert exc.code == "MODULE_NOT_FOUND"
    else:  # pragma: no cover
        raise AssertionError("expected ModuleError")
    assert manager.install_calls == 0


def test_engine_status_exposes_model_card(client: TestClient) -> None:
    card = client.get("/api/v1/engine").json()["modelCard"]
    assert card["id"] == "cardia-2.0"
    assert card["classes"] == ["N", "SVEB", "VEB", "F"]
    assert card["input"]["leads"] == ["MLII"]
    assert card["nonDiagnostic"] is True
    assert card["limitations"]

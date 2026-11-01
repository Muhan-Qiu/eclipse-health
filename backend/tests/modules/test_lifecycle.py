"""安装 → 启用 → 启动 → 调用 → 审计 → 卸载 全链路，以及权限、崩溃、更新与并发。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from module_test_helpers import DEMO_ID, build_demo_package
from sqlalchemy.orm import Session

from eclipse_health_backend.modules.audit import AuditEvent
from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manager import ModuleManager


def _install_enabled(manager, package: Path) -> dict:
    summary = manager.install(package, enable=True)
    assert summary["id"] == DEMO_ID
    assert summary["enabled"] is True
    return summary


def test_first_run_is_empty(manager) -> None:
    assert manager.list_modules() == []
    assert manager.audit_events() == []


def test_full_lifecycle(manager, demo_package: Path) -> None:
    summary = manager.install(demo_package)
    assert summary["state"] == "installed"
    assert summary["requestedPermissions"] == ["files:user-selected"]
    assert summary["grantedPermissions"] == ["files:user-selected"]
    assert (manager.modules_root / DEMO_ID / "1.0.0" / "src" / "main.py").is_file()

    assert manager.enable(DEMO_ID)["state"] == "enabled"
    assert manager.start(DEMO_ID)["state"] == "running"
    secret = "waveform-secret-notes"
    result = manager.call(DEMO_ID, "echo", {"text": secret})
    assert result == {"text": secret, "length": len(secret)}
    assert manager.call(DEMO_ID, "hello", {"name": "eclipse"}) == {"message": "Hello, eclipse!"}

    assert manager.stop(DEMO_ID)["state"] == "stopped"
    assert manager.start(DEMO_ID)["state"] == "running"
    assert manager.disable(DEMO_ID)["state"] == "disabled"
    manager.uninstall(DEMO_ID, keep_data=False)
    assert manager.list_modules() == []
    assert not (manager.modules_root / DEMO_ID).exists()

    actions = [event["action"] for event in manager.audit_events(limit=200)]
    for action in ("module.install", "module.enable", "module.start", "rpc.call", "module.disable", "module.uninstall"):
        assert action in actions, actions

    serialized = json.dumps(manager.audit_events(limit=200), ensure_ascii=False)
    assert secret not in serialized, "审计不得记录调用参数内容"
    assert str(demo_package.parent) not in serialized, "审计不得记录绝对路径"


def test_state_persists_across_manager_restart(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    assert manager.call(DEMO_ID, "echo", {"text": "before"})["text"] == "before"
    manager.shutdown()

    restarted = ModuleManager(data_dir=manager.data_dir, engine=manager.engine, call_timeout_s=1.0)
    try:
        assert restarted.get_module(DEMO_ID)["state"] == "enabled"
        assert restarted.call(DEMO_ID, "echo", {"text": "after"})["text"] == "after"
    finally:
        restarted.shutdown()


def test_call_lazily_starts_worker(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    assert manager.get_module(DEMO_ID)["state"] == "enabled"
    assert manager.call(DEMO_ID, "echo", {"text": "lazy"})["length"] == 4
    assert manager.get_module(DEMO_ID)["state"] == "running"


def test_disabled_module_rejects_rpc(manager, demo_package: Path) -> None:
    manager.install(demo_package)
    with pytest.raises(ModuleError) as info:
        manager.call(DEMO_ID, "echo", {"text": "x"})
    assert info.value.code == "MODULE_DISABLED"


def test_permissions_gate_core_calls(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    assert manager.call(DEMO_ID, "echo", {"text": "warm"})["text"] == "warm"

    # 已授权：通过权限检查后，B1 尚未接线核心数据方法。
    with pytest.raises(ModuleError) as allowed:
        manager.call(DEMO_ID, "call_core", {"method": "files.pick", "params": {}})
    assert allowed.value.code == "NOT_IMPLEMENTED"

    # 未请求的权限：默认拒绝。
    with pytest.raises(ModuleError) as denied:
        manager.call(DEMO_ID, "call_core", {"method": "records.query", "params": {}})
    assert denied.value.code == "PERMISSION_DENIED"

    revoked = manager.revoke_permission(DEMO_ID, "files:user-selected")
    assert revoked["granted"] == []
    assert revoked["available"] == ["files:user-selected"]
    assert manager.get_module(DEMO_ID)["state"] == "stopped"

    with pytest.raises(ModuleError) as denied_after:
        manager.call(DEMO_ID, "call_core", {"method": "files.pick", "params": {}})
    assert denied_after.value.code == "PERMISSION_DENIED"

    granted = manager.grant_permission(DEMO_ID, "files:user-selected")
    assert granted["granted"] == ["files:user-selected"]
    with pytest.raises(ModuleError) as allowed_again:
        manager.call(DEMO_ID, "call_core", {"method": "files.pick", "params": {}})
    assert allowed_again.value.code == "NOT_IMPLEMENTED"

    actions = [event["action"] for event in manager.audit_events(limit=200)]
    assert "permission.revoke" in actions
    assert "permission.grant" in actions
    assert "core.call" in actions


def test_crash_is_detected_and_restarted_once(manager, demo_package: Path) -> None:
    # 默认崩溃预算已改为 3 次（契约 §5，B2-01）；本测试只验证「重启一次后不再重启」的机制。
    manager.max_restarts = 1
    _install_enabled(manager, demo_package)
    manager.start(DEMO_ID)
    with pytest.raises(ModuleError) as info:
        manager.call(DEMO_ID, "fail", {"mode": "crash"})
    assert info.value.code == "MODULE_CRASH"
    assert manager.get_module(DEMO_ID)["state"] == "running"
    assert manager.call(DEMO_ID, "echo", {"text": "back"})["text"] == "back"

    # 连续第二次崩溃：不再自动重启。
    with pytest.raises(ModuleError) as first:
        manager.call(DEMO_ID, "fail", {"mode": "crash"})
    assert first.value.code == "MODULE_CRASH"
    with pytest.raises(ModuleError) as second:
        manager.call(DEMO_ID, "fail", {"mode": "crash"})
    assert second.value.code == "MODULE_CRASH"
    assert manager.get_module(DEMO_ID)["state"] == "crashed"
    with pytest.raises(ModuleError) as blocked:
        manager.call(DEMO_ID, "echo", {"text": "no"})
    assert blocked.value.code == "MODULE_CRASH"

    assert manager.start(DEMO_ID)["state"] == "running"
    assert manager.call(DEMO_ID, "echo", {"text": "recovered"})["text"] == "recovered"

    actions = [event["action"] for event in manager.audit_events(limit=200)]
    assert "module.crash" in actions
    assert "module.restart" in actions


def test_idle_worker_death_is_detected(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    manager.start(DEMO_ID)
    host = manager._hosts[DEMO_ID]
    assert host._process is not None
    host._process.kill()
    host._process.wait(timeout=5)

    assert manager.get_module(DEMO_ID)["state"] == "crashed"
    assert manager.call(DEMO_ID, "echo", {"text": "revived"})["text"] == "revived"
    assert "module.crash" in [event["action"] for event in manager.audit_events(limit=200)]


def test_timeout_is_reported_and_module_can_restart(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    manager.start(DEMO_ID)
    with pytest.raises(ModuleError) as info:
        manager.call(DEMO_ID, "fail", {"mode": "timeout"})
    assert info.value.code == "MODULE_TIMEOUT"
    assert manager.get_module(DEMO_ID)["state"] == "stopped"
    assert manager.start(DEMO_ID)["state"] == "running"
    assert manager.call(DEMO_ID, "echo", {"text": "alive"})["text"] == "alive"


def test_update_keeps_old_version_and_rollback(manager, tmp_path: Path) -> None:
    v1 = build_demo_package(tmp_path, version="1.0.0")
    v2 = build_demo_package(tmp_path, version="1.0.1")
    _install_enabled(manager, v1)
    updated = manager.install(v2)
    assert updated["version"] == "1.0.1"
    assert updated["previousVersion"] == "1.0.0"
    assert (manager.modules_root / DEMO_ID / "1.0.0").is_dir()
    assert (manager.modules_root / DEMO_ID / "1.0.1").is_dir()
    assert manager.call(DEMO_ID, "echo", {"text": "v2"})["text"] == "v2"

    rolled_back = manager.rollback(DEMO_ID)
    assert rolled_back["version"] == "1.0.0"
    assert rolled_back["previousVersion"] == "1.0.1"
    assert manager.call(DEMO_ID, "echo", {"text": "v1"})["text"] == "v1"
    assert "module.rollback" in [event["action"] for event in manager.audit_events(limit=200)]


def test_records_delete_is_not_granted_by_default(manager, tmp_path: Path) -> None:
    package = build_demo_package(
        tmp_path, permissions=["files:user-selected", "records:delete"]
    )
    summary = manager.install(package)
    assert summary["requestedPermissions"] == ["files:user-selected", "records:delete"]
    assert summary["grantedPermissions"] == ["files:user-selected"]
    granted = manager.grant_permission(DEMO_ID, "records:delete")
    assert granted["granted"] == ["files:user-selected", "records:delete"]


def test_update_reports_new_permissions_without_auto_grant(manager, tmp_path: Path) -> None:
    v1 = build_demo_package(tmp_path, version="1.0.0")
    v2 = build_demo_package(tmp_path, version="1.0.1", permissions=["files:user-selected", "records:read"])
    _install_enabled(manager, v1)
    updated = manager.install(v2)
    assert updated["addedPermissions"] == ["records:read"]
    assert updated["grantedPermissions"] == ["files:user-selected"]
    assert "records:read" in updated["requestedPermissions"]


def test_install_same_version_conflicts(manager, demo_package: Path) -> None:
    manager.install(demo_package)
    with pytest.raises(ModuleError) as info:
        manager.install(demo_package)
    assert info.value.code == "MODULE_ALREADY_INSTALLED"


def test_concurrent_install_same_package(manager, demo_package: Path) -> None:
    def attempt() -> str:
        try:
            manager.install(demo_package)
            return "ok"
        except ModuleError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(lambda _: attempt(), range(2)))
    assert results == ["MODULE_ALREADY_INSTALLED", "ok"]


def test_uninstall_keep_data(manager, demo_package: Path) -> None:
    manager.install(demo_package)
    data_file = manager.modules_root / DEMO_ID / "data" / "notes.txt"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("local only", encoding="utf-8")

    manager.uninstall(DEMO_ID, keep_data=True)
    assert data_file.is_file()
    assert manager.list_modules() == []
    assert manager.audit_events(action="module.uninstall")[0]["detail"]["keepData"] is True

    manager.install(demo_package)
    manager.uninstall(DEMO_ID, keep_data=False)
    assert not (manager.modules_root / DEMO_ID).exists()


def test_audit_is_append_only(manager, demo_package: Path) -> None:
    manager.install(demo_package)
    event_id = manager.audit_events()[0]["id"]
    with Session(manager.engine) as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None
        session.delete(event)
        with pytest.raises(RuntimeError):
            session.commit()


def test_unknown_module_errors(manager) -> None:
    with pytest.raises(ModuleError) as info:
        manager.enable("org.eclipsehealth.missing")
    assert info.value.code == "MODULE_NOT_FOUND"
    with pytest.raises(ModuleError) as uninstall:
        manager.uninstall("org.eclipsehealth.missing")
    assert uninstall.value.code == "MODULE_NOT_FOUND"
    assert manager.audit_events() == []


def test_audit_filters(manager, demo_package: Path) -> None:
    _install_enabled(manager, demo_package)
    manager.start(DEMO_ID)
    manager.call(DEMO_ID, "echo", {"text": "audit"})

    install_events = manager.audit_events(module_id=DEMO_ID, action="module.install")
    assert len(install_events) == 1
    detail = install_events[0]["detail"]
    assert detail["version"] == "1.0.0"
    assert "bytes" in detail
    assert detail["grantedPermissions"] == ["files:user-selected"]
    assert install_events[0]["createdAt"].endswith("Z")

    rpc_events = manager.audit_events(action="rpc.call")
    assert rpc_events
    assert all(event["detail"]["method"] == "echo" for event in rpc_events)
    assert all("durationMs" in event["detail"] and event["detail"]["ok"] is True for event in rpc_events)

    now = datetime.now(UTC)
    assert manager.audit_events(since=now + timedelta(minutes=1)) == []
    assert manager.audit_events(until=now - timedelta(minutes=1)) == []
    assert manager.audit_events(since=now - timedelta(minutes=1), until=now + timedelta(minutes=1))
    assert manager.audit_events(module_id="org.eclipsehealth.other") == []
    assert manager.audit_events(action="not.an.action") == []
    assert manager.audit_events(limit=1)

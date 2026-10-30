"""贡献注册表测试：enabled/权限过滤、聚合字段、API 形状与不启动 worker。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from module_test_helpers import DEMO_ID, build_demo_package

from eclipse_health_backend.modules.contributions import CONTRIBUTION_KINDS, collect_contributions
from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manager import ModuleManager

PREFIX = "/api/v1/modules"
WIDGETS_ID = "org.eclipsehealth.demo.widgets"
HEALTH_ID = "org.eclipsehealth.demo.health"


def _widget_updates() -> dict:
    return {
        "id": WIDGETS_ID,
        "name": "Demo Widgets",
        "description": "Dashboard widget fixture.",
        "type": "dashboard-widget",
        "permissions": [],
        "contributes": {
            "ui": {
                "widgets": [
                    {
                        "id": "weight-trend",
                        "title": "体重趋势",
                        "size": "md",
                        "dataSource": {"type": "module-rpc", "method": "stats"},
                        "view": {"type": "sparkline", "unit": "kg", "valuePath": "latest.weight"},
                    }
                ],
                "pages": [{"id": "weight", "title": "体重", "layout": [{"component": "text", "text": "hi"}]}],
            }
        },
    }


def _install_enabled(manager: ModuleManager, package: Path) -> dict:
    summary = manager.install(package, enable=True)
    assert summary["enabled"] is True
    return summary


def test_empty_registry(manager: ModuleManager) -> None:
    result = collect_contributions(manager)
    assert set(CONTRIBUTION_KINDS) <= set(result)
    assert result["counts"] == {kind: 0 for kind in CONTRIBUTION_KINDS}
    for kind in CONTRIBUTION_KINDS:
        assert result[kind] == []


def test_disabled_modules_are_filtered(manager: ModuleManager, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path, manifest_updates=_widget_updates())
    manager.install(package)  # 默认不启用
    assert collect_contributions(manager)["counts"]["widgets"] == 0

    manager.enable(WIDGETS_ID)
    widgets = collect_contributions(manager, kind="widgets")["items"]
    assert [widget["id"] for widget in widgets] == ["weight-trend"]


def test_aggregation_carries_module_identity(manager: ModuleManager, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path, manifest_updates=_widget_updates())
    _install_enabled(manager, package)

    widget = collect_contributions(manager, kind="widgets")["items"][0]
    assert widget["moduleId"] == WIDGETS_ID
    assert widget["moduleName"] == "Demo Widgets"
    assert widget["moduleVersion"] == "1.0.0"
    assert widget["moduleType"] == "dashboard-widget"
    assert widget["view"]["type"] == "sparkline"

    page = collect_contributions(manager, kind="pages")["items"][0]
    assert page["moduleId"] == WIDGETS_ID


def test_record_types_are_aggregated(manager: ModuleManager, tmp_path: Path) -> None:
    updates = {
        "id": HEALTH_ID,
        "name": "Demo Health",
        "type": "health-domain",
        "permissions": [],
        "contributes": {
            "recordTypes": [{"id": "weight", "name": "体重", "schema": {"type": "object"}}]
        },
    }
    package = build_demo_package(tmp_path, manifest_updates=updates)
    _install_enabled(manager, package)

    items = collect_contributions(manager, kind="recordTypes")["items"]
    assert [(item["id"], item["moduleId"]) for item in items] == [("weight", HEALTH_ID)]


def test_tools_require_llm_permission(manager: ModuleManager, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path, permissions=["llm", "records:read"])
    _install_enabled(manager, package)
    assert collect_contributions(manager)["counts"]["tools"] == 1

    manager.revoke_permission(DEMO_ID, "llm")
    assert collect_contributions(manager, kind="tools")["items"] == []

    manager.grant_permission(DEMO_ID, "llm")
    tool = collect_contributions(manager, kind="tools")["items"][0]
    assert tool["moduleId"] == DEMO_ID
    assert tool["moduleType"] == "ai-tool"
    assert tool["inputSchema"]["required"] == ["text"]


def test_tool_parameters_alias_is_normalized(manager: ModuleManager, tmp_path: Path) -> None:
    updates = {
        "contributes": {
            "tools": [
                {
                    "id": "alias.tool",
                    "name": "Alias",
                    "description": "Uses the parameters alias.",
                    "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}},
                }
            ]
        }
    }
    package = build_demo_package(tmp_path, manifest_updates=updates, permissions=["llm"])
    _install_enabled(manager, package)

    tool = collect_contributions(manager, kind="tools")["items"][0]
    assert tool["inputSchema"] == {"type": "object", "properties": {"days": {"type": "integer"}}}
    assert "parameters" not in tool


def test_kind_filter_shape_and_unknown_kind(manager: ModuleManager) -> None:
    assert collect_contributions(manager, kind="widgets") == {"type": "widgets", "items": []}
    with pytest.raises(ModuleError) as info:
        collect_contributions(manager, kind="commands")
    assert info.value.code == "INVALID_INPUT"
    assert info.value.detail["allowed"] == list(CONTRIBUTION_KINDS)


def test_registry_does_not_start_workers(manager: ModuleManager, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path, permissions=["llm"])
    _install_enabled(manager, package)

    collect_contributions(manager)

    actions = [event["action"] for event in manager.audit_events(limit=100)]
    assert "module.start" not in actions
    assert "rpc.call" not in actions


def _install_via_api(client: TestClient, package: Path, *, enable: bool = True) -> dict:
    response = client.post(
        f"{PREFIX}/install", json={"path": str(package), "enable": enable}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_api_returns_grouped_contributions(api_client: TestClient, demo_package: Path) -> None:
    empty = api_client.get(f"{PREFIX}/contributions")
    assert empty.status_code == 200
    assert empty.json()["counts"] == {kind: 0 for kind in CONTRIBUTION_KINDS}

    _install_via_api(api_client, demo_package)
    assert api_client.get(f"{PREFIX}/contributions").json()["counts"]["tools"] == 0


def test_api_contributions_type_filter(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(tmp_path, permissions=["llm"])
    _install_via_api(api_client, package)

    tools = api_client.get(f"{PREFIX}/contributions", params={"type": "tools"}).json()
    assert tools["type"] == "tools"
    assert tools["items"][0]["moduleId"] == DEMO_ID

    invalid = api_client.get(f"{PREFIX}/contributions", params={"type": "commands"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_INPUT"


def test_api_disabled_module_contributes_nothing(api_client: TestClient, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path, manifest_updates=_widget_updates())
    _install_via_api(api_client, package, enable=False)

    result = api_client.get(f"{PREFIX}/contributions").json()
    assert result["counts"]["widgets"] == 0

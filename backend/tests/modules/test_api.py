"""REST 路由测试：路由挂载、状态、错误码与审计过滤。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from module_test_helpers import DEMO_ID

PREFIX = "/api/v1/modules"


def _install(client: TestClient, package: Path, *, enable: bool = True) -> dict:
    response = client.post(f"{PREFIX}/install", json={"path": str(package), "enable": enable})
    assert response.status_code == 200, response.text
    return response.json()


def test_install_list_start_rpc_audit_uninstall(api_client: TestClient, demo_package: Path) -> None:
    installed = _install(api_client, demo_package)
    assert installed["id"] == DEMO_ID
    assert installed["state"] == "enabled"

    listing = api_client.get(PREFIX).json()
    assert [item["id"] for item in listing["modules"]] == [DEMO_ID]

    started = api_client.post(f"{PREFIX}/{DEMO_ID}/start")
    assert started.status_code == 200
    assert started.json()["state"] == "running"

    called = api_client.post(f"{PREFIX}/{DEMO_ID}/rpc", json={"method": "echo", "params": {"text": "api"}})
    assert called.status_code == 200
    assert called.json()["result"] == {"text": "api", "length": 3}

    events = api_client.get(f"{PREFIX}/audit", params={"moduleId": DEMO_ID, "action": "rpc.call"}).json()
    assert events["count"] == 1
    assert events["events"][0]["detail"]["method"] == "echo"

    assert api_client.get(f"{PREFIX}/{DEMO_ID}").status_code == 200
    deleted = api_client.delete(f"{PREFIX}/{DEMO_ID}", params={"keepData": "true"})
    assert deleted.status_code == 200
    assert deleted.json()["uninstalled"] is True
    assert api_client.get(f"{PREFIX}/{DEMO_ID}").status_code == 404


def test_permission_endpoints(api_client: TestClient, demo_package: Path) -> None:
    _install(api_client, demo_package)
    permissions = api_client.get(f"{PREFIX}/{DEMO_ID}/permissions").json()
    assert permissions["requested"] == ["files:user-selected"]
    assert permissions["granted"] == ["files:user-selected"]

    revoked = api_client.delete(f"{PREFIX}/{DEMO_ID}/permissions/files:user-selected").json()
    assert revoked["granted"] == []

    granted = api_client.post(f"{PREFIX}/{DEMO_ID}/permissions/files:user-selected").json()
    assert granted["granted"] == ["files:user-selected"]

    unknown = api_client.post(f"{PREFIX}/{DEMO_ID}/permissions/records:delete")
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "INVALID_INPUT"


def test_error_codes(api_client: TestClient, demo_package: Path, tmp_path: Path) -> None:
    missing = api_client.post(f"{PREFIX}/install", json={"path": str(tmp_path / "nope.ehmod")})
    assert missing.status_code == 422
    assert missing.json()["code"] == "INVALID_INPUT"

    unknown = api_client.get(f"{PREFIX}/org.eclipsehealth.missing")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "MODULE_NOT_FOUND"

    _install(api_client, demo_package, enable=False)

    disabled_rpc = api_client.post(f"{PREFIX}/{DEMO_ID}/rpc", json={"method": "echo", "params": {"text": "x"}})
    assert disabled_rpc.status_code == 409
    assert disabled_rpc.json()["code"] == "MODULE_DISABLED"

    enabled = api_client.post(f"{PREFIX}/{DEMO_ID}/enable")
    assert enabled.status_code == 200

    failed = api_client.post(f"{PREFIX}/{DEMO_ID}/rpc", json={"method": "fail", "params": {"mode": "error"}})
    assert failed.status_code == 502
    assert failed.json()["code"] == "MODULE_ERROR"

    denied = api_client.post(
        f"{PREFIX}/{DEMO_ID}/rpc",
        json={"method": "call_core", "params": {"method": "records.query", "params": {}}},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERMISSION_DENIED"


def test_audit_route_not_shadowed(api_client: TestClient) -> None:
    response = api_client.get(f"{PREFIX}/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["events"] == []
    assert body["count"] == 0
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert body["hasMore"] is False

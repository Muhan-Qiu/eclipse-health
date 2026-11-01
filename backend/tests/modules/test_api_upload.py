"""上传安装、权限确认与审计分页的 REST 测试（B4-06）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from module_test_helpers import DEMO_ID, build_demo_package

from eclipse_health_backend.modules import api as module_api

PREFIX = "/api/v1/modules"


def _files(package: Path, filename: str | None = None) -> dict[str, tuple[str, bytes, str]]:
    return {
        "file": (
            filename or package.name,
            package.read_bytes(),
            "application/octet-stream",
        )
    }


def _preview(client: TestClient, package: Path) -> dict[str, Any]:
    response = client.post(f"{PREFIX}/preview-upload", files=_files(package))
    assert response.status_code == 200, response.text
    return response.json()


def _install_upload(
    client: TestClient,
    package: Path,
    *,
    enable: bool = False,
    permissions: list[str] | None = None,
) -> dict[str, Any]:
    data: dict[str, str] = {"enable": "true" if enable else "false"}
    if permissions is not None:
        data["permissions"] = json.dumps(permissions)
    response = client.post(f"{PREFIX}/install-upload", files=_files(package), data=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_upload_returns_manifest_without_installing(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(
        tmp_path,
        permissions=["records:read", "records:delete", "network", "llm"],
        manifest_updates={"allowedHosts": ["example.com"]},
    )
    preview = _preview(api_client, package)

    assert preview["id"] == DEMO_ID
    assert preview["version"] == "1.0.0"
    assert preview["type"] == "ai-tool"
    assert preview["license"] == "GPL-3.0-only"
    assert preview["permissions"] == ["records:read", "records:delete", "network", "llm"]
    risks = {item["scope"]: item["risk"] for item in preview["permissionDetails"]}
    assert risks["records:delete"] == "high"
    assert risks["network"] == "high"
    assert risks["records:read"] == "low"
    assert preview["alreadyInstalled"] is False
    assert preview["newPermissions"] == []
    assert preview["packageBytes"] > 0
    # 不上传绝对路径、原文件名或 entry 路径。
    serialized = json.dumps(preview)
    assert str(tmp_path) not in serialized
    assert package.name not in serialized
    assert "entry" not in preview

    assert api_client.get(PREFIX).json()["modules"] == []


def test_permission_catalog_marks_risky_scopes(api_client: TestClient) -> None:
    catalog = api_client.get(f"{PREFIX}/permission-catalog").json()["permissions"]
    by_scope = {item["scope"]: item for item in catalog}
    assert len(catalog) == 11
    assert by_scope["records:delete"]["risk"] == "high"
    assert by_scope["network"]["risk"] == "high"
    assert by_scope["ui:custom"]["risk"] == "high"
    assert by_scope["records:read"]["risk"] == "low"
    assert all(item["label"] for item in catalog)


def test_install_upload_keeps_only_selected_permissions(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(
        tmp_path,
        permissions=["records:read", "records:delete", "network"],
        manifest_updates={"allowedHosts": ["example.com"]},
    )
    installed = _install_upload(api_client, package, permissions=["records:read"])

    assert installed["state"] == "installed"
    assert installed["requestedPermissions"] == [
        "records:read",
        "records:delete",
        "network",
    ]
    assert installed["grantedPermissions"] == ["records:read"]

    permissions = api_client.get(f"{PREFIX}/{DEMO_ID}/permissions").json()
    scopes = {item["scope"]: item for item in permissions["scopes"]}
    assert scopes["records:read"]["granted"] is True
    assert scopes["records:delete"]["granted"] is False
    assert scopes["network"]["risk"] == "high"
    assert permissions["available"] == ["network", "records:delete"]

    granted = api_client.post(f"{PREFIX}/{DEMO_ID}/permissions/records:delete").json()
    assert "records:delete" in granted["granted"]
    assert granted["scopes"][1]["granted"] is True

    events = api_client.get(
        f"{PREFIX}/audit", params={"moduleId": DEMO_ID, "action": "permission.grant"}
    ).json()
    assert events["count"] == 1
    assert events["events"][0]["scope"] == "records:delete"


def test_high_risk_requires_explicit_selection(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(tmp_path, permissions=["records:read", "records:delete"])

    default = _install_upload(api_client, package)
    assert default["grantedPermissions"] == ["records:read"]

    api_client.delete(f"{PREFIX}/{DEMO_ID}", params={"keepData": "false"})
    selected = _install_upload(
        api_client, package, permissions=["records:read", "records:delete"]
    )
    assert selected["grantedPermissions"] == ["records:delete", "records:read"]

    revoked = api_client.delete(f"{PREFIX}/{DEMO_ID}/permissions/records:delete").json()
    assert revoked["granted"] == ["records:read"]


def test_install_upload_rejects_unknown_scope_before_install(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(tmp_path, permissions=["records:read"])
    response = api_client.post(
        f"{PREFIX}/install-upload",
        files=_files(package),
        data={"permissions": json.dumps(["llm"])},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INPUT"
    assert response.json()["details"]["unknown"] == ["llm"]
    assert api_client.get(PREFIX).json()["modules"] == []


def test_upload_rejects_bad_package_extension_and_size(
    api_client: TestClient, tmp_path: Path, monkeypatch: Any
) -> None:
    not_zip = tmp_path / "broken.ehmod"
    not_zip.write_bytes(b"definitely not a zip archive")
    response = api_client.post(f"{PREFIX}/preview-upload", files=_files(not_zip))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PACKAGE"

    package = build_demo_package(tmp_path)
    wrong_ext = api_client.post(
        f"{PREFIX}/preview-upload", files=_files(package, filename="demo.zip")
    )
    assert wrong_ext.status_code == 422
    assert wrong_ext.json()["code"] == "INVALID_INPUT"

    monkeypatch.setattr(module_api, "MAX_UPLOAD_BYTES", 8)
    oversized = api_client.post(f"{PREFIX}/install-upload", files=_files(package))
    assert oversized.status_code == 507
    assert oversized.json()["code"] == "RESOURCE_EXCEEDED"


def test_preview_reports_incompatible_version(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(
        tmp_path, manifest_updates={"engines": {"eclipse": ">=9.0 <10.0"}}
    )
    response = api_client.post(f"{PREFIX}/preview-upload", files=_files(package))
    assert response.status_code == 409
    assert response.json()["code"] == "INCOMPATIBLE_API"


def test_manifest_endpoint_projects_contributions(api_client: TestClient, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path)
    _install_upload(api_client, package)

    manifest = api_client.get(f"{PREFIX}/{DEMO_ID}/manifest")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["author"]["name"] == "eclipse health"
    assert body["resources"]["memoryMb"] == 64
    assert body["contributes"]["tools"][0]["id"] == "demo.echo"
    assert body["permissionDetails"][0]["scope"] == "files:user-selected"
    assert "entry" not in body
    assert str(tmp_path) not in json.dumps(body)


def test_uninstall_keeps_or_removes_module_data(
    api_client: TestClient, tmp_path: Path, module_data_dir: Path
) -> None:
    package = build_demo_package(tmp_path)
    data_file = module_data_dir / "modules" / DEMO_ID / "data" / "sentinel.txt"

    _install_upload(api_client, package)
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("keep me", encoding="utf-8")
    kept = api_client.delete(f"{PREFIX}/{DEMO_ID}", params={"keepData": "true"})
    assert kept.status_code == 200
    assert kept.json()["keptData"] is True
    assert data_file.read_text(encoding="utf-8") == "keep me"

    _install_upload(api_client, package)
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("delete me", encoding="utf-8")
    removed = api_client.delete(f"{PREFIX}/{DEMO_ID}", params={"keepData": "false"})
    assert removed.status_code == 200
    assert not data_file.exists()


def test_audit_pagination_and_filters(api_client: TestClient, tmp_path: Path) -> None:
    package = build_demo_package(tmp_path)
    _install_upload(api_client, package)
    api_client.delete(f"{PREFIX}/{DEMO_ID}/permissions/files:user-selected")
    api_client.post(f"{PREFIX}/{DEMO_ID}/permissions/files:user-selected")

    first = api_client.get(
        f"{PREFIX}/audit", params={"moduleId": DEMO_ID, "limit": 1}
    ).json()
    assert first["count"] == 1
    assert first["limit"] == 1
    assert first["offset"] == 0
    assert first["hasMore"] is True

    second = api_client.get(
        f"{PREFIX}/audit", params={"moduleId": DEMO_ID, "limit": 1, "offset": 1}
    ).json()
    assert second["count"] == 1
    assert second["events"][0]["id"] != first["events"][0]["id"]

    grants = api_client.get(
        f"{PREFIX}/audit", params={"action": "permission.grant"}
    ).json()
    assert grants["count"] == 1
    assert grants["events"][0]["action"] == "permission.grant"

    empty = api_client.get(
        f"{PREFIX}/audit", params={"since": "2999-01-01T00:00:00Z"}
    ).json()
    assert empty["events"] == []


def test_preview_upgrade_lists_only_new_permissions(
    api_client: TestClient, tmp_path: Path
) -> None:
    _install_upload(
        api_client, build_demo_package(tmp_path, version="1.0.0", permissions=["records:read"])
    )
    upgraded = build_demo_package(
        tmp_path,
        version="1.0.1",
        permissions=["records:read", "network"],
        manifest_updates={"allowedHosts": ["example.com"]},
    )
    preview = _preview(api_client, upgraded)
    assert preview["alreadyInstalled"] is True
    assert preview["installedVersion"] == "1.0.0"
    assert preview["newPermissions"] == ["network"]


def test_install_upload_without_selection_denies_core_call(
    api_client: TestClient, tmp_path: Path
) -> None:
    package = build_demo_package(tmp_path, permissions=["records:read"])
    installed = _install_upload(api_client, package, enable=True, permissions=[])
    assert installed["grantedPermissions"] == []

    api_client.post(f"{PREFIX}/{DEMO_ID}/start")
    denied = api_client.post(
        f"{PREFIX}/{DEMO_ID}/rpc",
        json={"method": "call_core", "params": {"method": "records.query", "params": {}}},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERMISSION_DENIED"

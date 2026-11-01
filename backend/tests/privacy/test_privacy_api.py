"""隐私中心：存储用量、确认令牌、清空范围、设置持久化与遥测。"""

from __future__ import annotations

import json

import pytest
from privacy_helpers import create_record

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.privacy.settings_store import settings_path
from eclipse_health_backend.settings import get_settings


@pytest.fixture(autouse=True)
def _clean_settings_file():
    settings_path().unlink(missing_ok=True)
    yield
    settings_path().unlink(missing_ok=True)


def _purge(client, token: str = "DELETE_ALL"):
    return client.delete(f"/api/v1/privacy/all?confirm={token}")


def test_storage_reports_counts_and_bytes(client, default_member):
    record = create_record(client, default_member["id"])
    response = client.get("/api/v1/privacy/storage")
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["records"] == 1
    assert body["counts"]["signals"] == 1
    assert body["counts"]["members"] == 1
    assert body["bytes"]["signals"] > 0
    assert body["bytes"]["total"] >= body["bytes"]["signals"]
    assert body["localOnly"] is True
    assert body["telemetry"] is False
    assert body["dataDir"] == str(get_settings().data_dir)
    assert record["id"]


def test_purge_requires_confirmation_token(client, default_member):
    create_record(client, default_member["id"])
    missing = client.delete("/api/v1/privacy/all")
    assert missing.status_code == 422
    wrong = _purge(client, "please")
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "confirmation_required"
    # 未确认时数据仍在。
    assert client.get("/api/v1/privacy/storage").json()["counts"]["records"] == 1


def test_purge_clears_health_data_but_keeps_members_and_settings(
    client, default_member
):
    client.put("/api/v1/settings", json={"closeToTray": False, "locale": "en-US"})
    create_record(client, default_member["id"], notes="要删除的备注")
    response = _purge(client)
    assert response.status_code == 200, response.text
    deleted = response.json()["deleted"]
    assert deleted["records"] == 1
    assert deleted["signals"] == 1
    assert "members" not in deleted

    storage = client.get("/api/v1/privacy/storage").json()
    assert storage["counts"]["records"] == 0
    assert storage["counts"]["signals"] == 0
    assert storage["counts"]["analyses"] == 0
    assert storage["counts"]["measurements"] == 0
    assert storage["counts"]["reports"] == 0
    assert storage["counts"]["members"] == 1
    assert storage["bytes"]["signals"] == 0

    members = client.get("/api/v1/members").json()
    assert len(members) == 1
    assert members[0]["displayName"] == default_member["displayName"]

    settings = client.get("/api/v1/settings").json()
    assert settings["closeToTray"] is False
    assert settings["locale"] == "en-US"


def test_purge_writes_append_only_audit_event(client, default_member):
    create_record(client, default_member["id"])
    assert _purge(client).status_code == 200
    from sqlmodel import select

    from eclipse_health_backend.modules.audit import AuditEvent

    with session_scope() as session:
        events = session.exec(
            select(AuditEvent).where(AuditEvent.action == "privacy.purge")
        ).all()
        assert events
        detail_json = events[-1].detail_json
    detail = json.loads(detail_json or "{}")
    # audit.sanitize_detail 会剔除 records/signals 等键，避免把数据内容写进审计。
    assert isinstance(detail.get("counts"), dict)
    assert "notes" not in json.dumps(detail)


def test_settings_defaults_and_roundtrip(client):
    defaults = client.get("/api/v1/settings").json()
    assert defaults == {
        "closeToTray": True,
        "splashEnabled": True,
        "telemetryEnabled": False,
        "locale": None,
    }

    updated = client.put(
        "/api/v1/settings",
        json={"closeToTray": False, "splashEnabled": False, "locale": "zh-CN"},
    )
    assert updated.status_code == 200
    assert updated.json()["closeToTray"] is False
    assert updated.json()["splashEnabled"] is False
    assert updated.json()["locale"] == "zh-CN"
    assert updated.json()["telemetryEnabled"] is False

    persisted = json.loads(settings_path().read_text(encoding="utf-8"))
    assert persisted["closeToTray"] is False
    assert persisted["telemetryEnabled"] is False

    again = client.get("/api/v1/settings").json()
    assert again == updated.json()


def test_telemetry_cannot_be_enabled(client):
    response = client.put("/api/v1/settings", json={"telemetryEnabled": True})
    assert response.status_code == 422
    assert response.json()["code"] == "telemetry_not_supported"
    assert client.get("/api/v1/settings").json()["telemetryEnabled"] is False


def test_invalid_locale_is_rejected(client):
    response = client.put("/api/v1/settings", json={"locale": "fr-FR"})
    assert response.status_code == 422


def test_corrupt_settings_file_falls_back_to_defaults(client):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    assert response.json()["telemetryEnabled"] is False
    assert response.json()["closeToTray"] is True

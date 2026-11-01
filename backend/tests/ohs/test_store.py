"""OHS 设置存储：DPAPI 加密、不可用拒绝、设置更新语义。"""

from __future__ import annotations

import json

import pytest
from ohs_helpers import requires_dpapi

from eclipse_health_backend.domain.errors import InvalidInputError
from eclipse_health_backend.ohs import store


def _raw_file() -> dict:
    return json.loads(store.config_path().read_text(encoding="utf-8"))


def test_missing_file_returns_unconfigured(clean_ohs: None) -> None:
    settings = store.public_settings()
    assert settings == {
        "configured": False,
        "baseUrl": "http://127.0.0.1:8080",
        "hasToken": False,
        "userId": None,
        "lastSync": None,
    }
    assert store.load_config().token == ""


def test_first_save_requires_token(clean_ohs: None) -> None:
    with pytest.raises(InvalidInputError) as excinfo:
        store.save_settings("http://127.0.0.1:8080")
    assert excinfo.value.code == "ohs_token_required"


@requires_dpapi
def test_token_is_encrypted_and_roundtrips(clean_ohs: None) -> None:
    saved = store.save_settings("http://127.0.0.1:8080/", "tenant-secret", "u1")
    assert saved["configured"] is True
    assert saved["hasToken"] is True
    assert saved["userId"] == "u1"

    raw_text = store.config_path().read_text(encoding="utf-8")
    assert "tenant-secret" not in raw_text
    raw = _raw_file()
    assert raw["token"]["scheme"] == "dpapi"
    assert raw["token"]["data"] != "tenant-secret"

    config = store.load_config()
    assert config.base_url == "http://127.0.0.1:8080"
    assert config.token == "tenant-secret"
    assert config.user_id == "u1"


@requires_dpapi
def test_save_without_token_keeps_existing_ciphertext(clean_ohs: None) -> None:
    store.save_settings("http://127.0.0.1:8080", "tenant-secret", "u1")
    cipher_before = _raw_file()["token"]["data"]

    store.save_settings("https://ohs.example.test", None, "u2")

    raw = _raw_file()
    assert raw["baseUrl"] == "https://ohs.example.test"
    assert raw["token"]["data"] == cipher_before
    assert store.load_config().token == "tenant-secret"
    assert store.load_config().user_id == "u2"


def test_invalid_url_not_written(clean_ohs: None) -> None:
    with pytest.raises(InvalidInputError):
        store.save_settings("ftp://example.test", "token")
    assert not store.config_path().exists()


@requires_dpapi
def test_dpapi_failure_refuses_plaintext(clean_ohs: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_secret: str) -> str:
        raise store.OhsStoreError("no dpapi", code="ohs_dpapi_unavailable")

    monkeypatch.setattr(store, "_protect", fail)
    with pytest.raises(store.OhsStoreError) as excinfo:
        store.save_settings("http://127.0.0.1:8080", "tenant-secret")
    assert excinfo.value.code == "ohs_dpapi_unavailable"
    assert not store.config_path().exists()


@requires_dpapi
def test_corrupt_ciphertext_reports_clear_error(clean_ohs: None) -> None:
    store.save_settings("http://127.0.0.1:8080", "tenant-secret")
    raw = _raw_file()
    raw["token"]["data"] = "not-base64!!"
    store.config_path().write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(store.OhsStoreError) as excinfo:
        store.load_config()
    assert excinfo.value.code == "ohs_token_unreadable"


@requires_dpapi
def test_last_sync_summary_roundtrip(clean_ohs: None) -> None:
    store.save_settings("http://127.0.0.1:8080", "tenant-secret")
    store.record_last_sync({"created": 3, "skipped": 1, "failed": 0, "warnings": []})
    assert store.public_settings()["lastSync"]["created"] == 3
    assert store.load_config().token == "tenant-secret"

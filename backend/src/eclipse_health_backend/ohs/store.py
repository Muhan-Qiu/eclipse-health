"""OHS 设置持久化：``<EH_DATA_DIR>/ohs.json``。

token 只以 Windows DPAPI 密文落盘；DPAPI 不可用时明确失败，拒绝保存明文。
文件里不保存任何健康数据，只保存连接参数与最近一次同步摘要。
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.errors import ApiError, InvalidInputError
from ..settings import get_settings
from ..storage.files import atomic_write_bytes
from .client import DEFAULT_BASE_URL, normalize_base_url

logger = logging.getLogger(__name__)

DPAPI_DESCRIPTION = "eclipse-health OHS token"
FILE_VERSION = 1


class OhsStoreError(ApiError):
    status_code = 500
    code = "ohs_store_error"


@dataclass(slots=True)
class OhsConfig:
    base_url: str
    token: str
    user_id: str | None
    last_sync: dict[str, Any] | None


def config_path() -> Path:
    return get_settings().data_dir / "ohs.json"


def _dpapi() -> Any:
    try:
        import win32crypt
    except Exception as exc:
        raise OhsStoreError(
            "当前系统不支持 Windows DPAPI，无法安全保存 OHS token",
            code="ohs_dpapi_unavailable",
        ) from exc
    return win32crypt


def _protect(secret: str) -> str:
    crypto = _dpapi()
    try:
        blob = crypto.CryptProtectData(
            secret.encode("utf-8"), DPAPI_DESCRIPTION, None, None, None, 0
        )
    except Exception as exc:
        raise OhsStoreError(
            "DPAPI 加密失败，未保存 token",
            code="ohs_dpapi_unavailable",
        ) from exc
    return base64.b64encode(blob).decode("ascii")


def _unprotect(ciphertext: str) -> str:
    crypto = _dpapi()
    try:
        blob = base64.b64decode(ciphertext.encode("ascii"), validate=True)
        _description, raw = crypto.CryptUnprotectData(blob, None, None, None, 0)
        return raw.decode("utf-8")
    except OhsStoreError:
        raise
    except Exception as exc:
        raise OhsStoreError(
            "无法解密已保存的 OHS token，请重新填写",
            code="ohs_token_unreadable",
        ) from exc


def _read_raw() -> dict[str, Any]:
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_bytes(config_path(), payload.encode("utf-8"))


def _ciphertext(raw: dict[str, Any]) -> str:
    token = raw.get("token")
    if not isinstance(token, dict) or token.get("scheme") != "dpapi":
        return ""
    value = token.get("data")
    return value if isinstance(value, str) else ""


def load_config() -> OhsConfig:
    raw = _read_raw()
    cached = raw.get("lastSync")
    base_url = raw.get("baseUrl")
    if not isinstance(base_url, str) or not base_url:
        base_url = DEFAULT_BASE_URL
    ciphertext = _ciphertext(raw)
    return OhsConfig(
        base_url=base_url,
        token=_unprotect(ciphertext) if ciphertext else "",
        user_id=raw.get("userId") if isinstance(raw.get("userId"), str) else None,
        last_sync=cached if isinstance(cached, dict) else None,
    )


def public_settings() -> dict[str, Any]:
    """返回给 UI 的安全视图：永不包含 token 或密文。"""
    raw = _read_raw()
    base_url = raw.get("baseUrl")
    if not isinstance(base_url, str) or not base_url:
        base_url = DEFAULT_BASE_URL
    last_sync = raw.get("lastSync")
    user_id = raw.get("userId")
    return {
        "configured": bool(_ciphertext(raw)),
        "baseUrl": base_url,
        "hasToken": bool(_ciphertext(raw)),
        "userId": user_id if isinstance(user_id, str) else None,
        "lastSync": last_sync if isinstance(last_sync, dict) else None,
    }


def save_settings(
    base_url: str,
    token: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """保存连接设置。

    ``token`` 为 ``None`` 或空串表示沿用已保存的密文；首次保存必须提供 token。
    """
    normalized = normalize_base_url(base_url)
    raw = _read_raw()
    ciphertext = _ciphertext(raw)
    fresh_token = (token or "").strip()
    if fresh_token:
        ciphertext = _protect(fresh_token)
    if not ciphertext:
        raise InvalidInputError(
            "请填写 OHS token 后再保存",
            code="ohs_token_required",
        )
    raw.update(
        {
            "version": FILE_VERSION,
            "baseUrl": normalized,
            "token": {"scheme": "dpapi", "data": ciphertext},
            "userId": (user_id or "").strip() or None,
        }
    )
    raw.setdefault("lastSync", None)
    _write_raw(raw)
    return public_settings()


def record_last_sync(summary: dict[str, Any]) -> None:
    """记录最近一次同步摘要；写入失败不阻断已经完成的同步。"""
    raw = _read_raw()
    raw["lastSync"] = summary
    raw.setdefault("version", FILE_VERSION)
    try:
        _write_raw(raw)
    except OSError:
        logger.warning("OHS last-sync summary could not be written", exc_info=True)


__all__ = [
    "FILE_VERSION",
    "OhsConfig",
    "OhsStoreError",
    "config_path",
    "load_config",
    "public_settings",
    "record_last_sync",
    "save_settings",
]

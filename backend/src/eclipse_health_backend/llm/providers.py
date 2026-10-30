"""Provider 配置与 API Key 存储（H3）。

安全约定（必须保持）：

- API Key 只以 Windows DPAPI 密文（``dpapi:v1:<base64>``）存在
  ``<data>/secrets/providers.json``，不落明文；
- 任何返回值、日志、异常都只带 provider 类型与 HTTP 状态，绝不带 key；
- DPAPI 使用当前用户作用域（``CRYPTPROTECT_UI_FORBIDDEN``），不需要额外密钥文件。

非 Windows 平台没有 DPAPI，写入 key 会抛 ``SecretError``；读取不含 key 的配置不受影响。
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from ..domain.common import utc_now
from ..domain.ids import uuid7
from ..settings import get_settings

logger = logging.getLogger(__name__)

ProviderKind = Literal["openai", "anthropic", "ollama", "mock"]
PROVIDER_KINDS: tuple[str, ...] = ("openai", "anthropic", "ollama", "mock")

DEFAULT_BASE_URLS: dict[str, str | None] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://127.0.0.1:11434",
    "mock": None,
}

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5",
    "ollama": "llama3.1",
    "mock": "mock-1",
}

STORE_VERSION = 1
KEY_PREFIX = "dpapi:v1:"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecretError(RuntimeError):
    """凭据存储失败；消息中不包含任何密文或明文。"""


class ProviderError(RuntimeError):
    """provider 校验/查询失败；``code`` 供 API 直接映射。"""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# DPAPI
# --------------------------------------------------------------------------- #

if os.name == "nt":  # pragma: no cover - 只在 Windows 上执行

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_uint32),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptProtectData.restype = ctypes.c_int
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptUnprotectData.restype = ctypes.c_int
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data: bytes) -> tuple[Any, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _take_blob(blob: Any) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def encrypt_secret(plaintext: str) -> str:
    """返回 ``dpapi:v1:<base64>``；调用方负责不把返回值写进日志。"""
    if not plaintext:
        raise SecretError("secret must not be empty")
    if os.name != "nt":
        raise SecretError("DPAPI credential storage is only available on Windows")

    data_in, _buffer_in = _blob(plaintext.encode("utf-8"))
    data_out = _DataBlob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(data_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        raise SecretError(f"DPAPI protect failed (error {ctypes.get_last_error()})")
    return KEY_PREFIX + base64.b64encode(_take_blob(data_out)).decode("ascii")


def decrypt_secret(key_ref: str) -> str:
    if not key_ref.startswith(KEY_PREFIX):
        raise SecretError("unsupported secret format")
    if os.name != "nt":
        raise SecretError("DPAPI credential storage is only available on Windows")

    try:
        cipher = base64.b64decode(key_ref[len(KEY_PREFIX) :], validate=True)
    except ValueError as exc:
        raise SecretError("corrupted secret payload") from exc

    data_in, _buffer_in = _blob(cipher)
    data_out = _DataBlob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        None,  # ppszDataDescr：不需要描述，传 NULL 省去一次 LocalFree
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        raise SecretError(f"DPAPI unprotect failed (error {ctypes.get_last_error()})")
    return _take_blob(data_out).decode("utf-8")


# --------------------------------------------------------------------------- #
# Provider 记录
# --------------------------------------------------------------------------- #


def new_provider_id() -> str:
    return f"llm_{uuid7()}"


@dataclass
class Provider:
    id: str
    kind: str
    label: str
    model: str
    base_url: str | None = None
    enabled: bool = True
    key_ref: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_storage(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "model": self.model,
            "baseUrl": self.base_url,
            "enabled": self.enabled,
            "keyRef": self.key_ref,
            "options": self.options,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def to_public(self) -> dict[str, Any]:
        """API 视图：只告诉前端「有没有配置 key」。"""
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "model": self.model,
            "baseUrl": self.base_url,
            "enabled": self.enabled,
            "configured": bool(self.key_ref),
            "isLocal": self.kind in {"ollama", "mock"},
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @property
    def needs_key(self) -> bool:
        return self.kind in {"openai", "anthropic"}


def _parse_provider(raw: dict[str, Any]) -> Provider | None:
    try:
        kind = str(raw["kind"])
        provider_id = str(raw["id"])
        label = str(raw.get("label") or kind)
        model = str(raw.get("model") or DEFAULT_MODELS.get(kind, "unknown"))
    except (KeyError, TypeError, ValueError):
        return None
    if kind not in PROVIDER_KINDS:
        return None
    base_url = raw.get("baseUrl")
    return Provider(
        id=provider_id,
        kind=kind,
        label=label,
        model=model,
        base_url=str(base_url) if base_url else None,
        enabled=bool(raw.get("enabled", True)),
        key_ref=str(raw["keyRef"]) if raw.get("keyRef") else None,
        options=dict(raw.get("options") or {}),
        created_at=str(raw.get("createdAt") or ""),
        updated_at=str(raw.get("updatedAt") or ""),
    )


def _validate_base_url(value: str | None, kind: str) -> str | None:
    if value is None or value == "":
        return DEFAULT_BASE_URLS.get(kind)
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("invalid_base_url", "baseUrl must be an http(s) URL")
    if parsed.username or parsed.password:
        # 拒绝把凭据写进 URL，避免随 provider 列表回显到界面
        raise ProviderError("invalid_base_url", "baseUrl must not contain credentials")
    if parsed.query or parsed.fragment:
        # 查询串常被用来夹带 token（?api_key=...），provider 列表会原样回显给前端，
        # 因此统一拒绝；网关参数请用 provider.options 或独立配置传递。
        raise ProviderError(
            "invalid_base_url", "baseUrl must not contain a query string or fragment"
        )
    return value.strip().rstrip("/")


class ProviderStore:
    """``providers.json`` 的读写；进程内加锁，写入走临时文件 + 原子替换。"""

    def __init__(self, path: Path | None = None) -> None:
        self._explicit_path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        if self._explicit_path is not None:
            return self._explicit_path
        return get_settings().data_dir / "secrets" / "providers.json"

    def _read_raw(self) -> list[dict[str, Any]]:
        path = self.path
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("providers store unreadable; treating as empty")
            return []
        items = payload.get("providers") if isinstance(payload, dict) else None
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _write_raw(self, providers: list[dict[str, Any]]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        data = json.dumps(
            {"version": STORE_VERSION, "providers": providers},
            ensure_ascii=False,
            indent=2,
        )
        temp.write_text(data, encoding="utf-8")
        os.replace(temp, path)
        if os.name != "nt":
            try:
                path.chmod(0o600)
            except OSError:  # pragma: no cover - 平台差异
                pass

    def list(self) -> list[Provider]:
        with self._lock:
            providers = [item for raw in self._read_raw() if (item := _parse_provider(raw))]
        return sorted(providers, key=lambda item: item.created_at, reverse=True)

    def get(self, provider_id: str) -> Provider:
        for provider in self.list():
            if provider.id == provider_id:
                return provider
        raise ProviderError(
            "provider_not_found", f"provider not found: {provider_id}", status_code=404
        )

    def find(self, provider_id: str) -> Provider | None:
        try:
            return self.get(provider_id)
        except ProviderError:
            return None

    def upsert(
        self,
        provider_id: str,
        payload: dict[str, Any],
        *,
        api_key: str | None,
        clear_key: bool = False,
    ) -> Provider:
        """新建或更新；``api_key=None`` 表示保持原 key 不变。"""
        if not provider_id or len(provider_id) > 64:
            raise ProviderError("invalid_provider_id", "provider id is invalid")
        if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in provider_id):
            raise ProviderError("invalid_provider_id", "provider id is invalid")

        with self._lock:
            raw_items = self._read_raw()
            existing: Provider | None = None
            for raw in raw_items:
                if raw.get("id") == provider_id:
                    existing = _parse_provider(raw)
                    break

            kind = str(payload.get("kind") or (existing.kind if existing else "")).strip()
            if kind not in PROVIDER_KINDS:
                raise ProviderError(
                    "invalid_provider_kind",
                    "kind must be one of openai, anthropic, ollama, mock",
                )

            label = str(
                payload.get("label")
                or (existing.label if existing else "")
                or {
                    "openai": "OpenAI",
                    "anthropic": "Anthropic",
                    "ollama": "本地 Ollama",
                    "mock": "演示 Mock",
                }[kind]
            ).strip()
            model = str(
                payload.get("model")
                or (existing.model if existing else "")
                or DEFAULT_MODELS[kind]
            ).strip()
            if not label or not model or len(label) > 80 or len(model) > 120:
                raise ProviderError("invalid_provider", "label/model is invalid")

            base_url = _validate_base_url(
                payload.get("baseUrl", existing.base_url if existing else None), kind
            )
            enabled = bool(payload.get("enabled", existing.enabled if existing else True))

            key_ref = existing.key_ref if existing else None
            if clear_key:
                key_ref = None
            if api_key is not None:
                key_ref = encrypt_secret(api_key) if api_key else None

            now = utc_now().isoformat()
            provider = Provider(
                id=provider_id,
                kind=kind,
                label=label,
                model=model,
                base_url=base_url,
                enabled=enabled,
                key_ref=key_ref,
                options=dict(existing.options) if existing else {},
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )

            merged = [raw for raw in raw_items if raw.get("id") != provider_id]
            merged.append(provider.to_storage())
            self._write_raw(merged)
        logger.info(
            "provider saved id=%s kind=%s model=%s key=%s",
            provider.id,
            provider.kind,
            provider.model,
            "configured" if provider.key_ref else "none",
        )
        return provider

    def delete(self, provider_id: str) -> None:
        with self._lock:
            raw_items = self._read_raw()
            kept = [raw for raw in raw_items if raw.get("id") != provider_id]
            if len(kept) == len(raw_items):
                raise ProviderError(
                    "provider_not_found", f"provider not found: {provider_id}", status_code=404
                )
            self._write_raw(kept)
        logger.info("provider deleted id=%s", provider_id)

    def resolve_api_key(self, provider: Provider) -> str | None:
        if not provider.key_ref:
            return None
        try:
            return decrypt_secret(provider.key_ref)
        except SecretError as exc:
            # 只记录原因类别，不记录密文
            logger.error("provider key unavailable id=%s reason=%s", provider.id, exc)
            raise ProviderError(
                "key_unavailable",
                "stored API key could not be decrypted",
                status_code=500,
            ) from exc


_default_store: ProviderStore | None = None
_store_lock = threading.Lock()


def get_provider_store() -> ProviderStore:
    """进程内单例；路径随 ``EH_DATA_DIR`` 延迟解析，测试无需清缓存。"""
    global _default_store
    with _store_lock:
        if _default_store is None:
            _default_store = ProviderStore()
        return _default_store


__all__ = [
    "DEFAULT_BASE_URLS",
    "DEFAULT_MODELS",
    "PROVIDER_KINDS",
    "Provider",
    "ProviderError",
    "ProviderStore",
    "SecretError",
    "decrypt_secret",
    "encrypt_secret",
    "get_provider_store",
    "new_provider_id",
]

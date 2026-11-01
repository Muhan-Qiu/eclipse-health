"""索引读取、Ed25519 验签、条目校验与 10 分钟缓存。"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import ValidationError as PydanticValidationError

from ..modules.semver import Version, parse_version
from .config import MarketplaceConfig
from .errors import MarketplaceError, validate_source
from .models import MarketplaceEntry, MarketplaceIndex

MAX_INDEX_BYTES = 5 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
FETCH_TIMEOUT_S = 15.0
CACHE_TTL_S = 600.0
MAX_REDIRECTS = 5

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_PEM_BEGIN = "-----BEGIN PUBLIC KEY-----"
_PEM_END = "-----END PUBLIC KEY-----"

ClientFactory = Callable[[], httpx.Client]

_cache: dict[str, tuple[float, MarketplaceIndex]] = {}
_cache_lock = threading.Lock()


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """签名覆盖除 signature 外的整个对象，规则见索引格式说明。"""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def load_public_keys(path: Path) -> dict[str, Ed25519PublicKey]:
    """解析内置公钥表：``keyId=<id>`` 行后跟 PEM 块，或 ``hex=<64 hex>``。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarketplaceError(
            "marketplace_signature_invalid",
            "内置市场公钥不可用，无法校验索引",
            {"reason": "public_key_missing"},
        ) from exc

    keys: dict[str, Ed25519PublicKey] = {}
    current_id: str | None = None
    pem_lines: list[str] = []
    in_pem = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not in_pem and line.startswith("keyId="):
            value = line.split("=", 1)[1].strip()
            current_id = value if KEY_ID_RE.match(value) else None
            continue
        if not in_pem and line.startswith("hex="):
            value = line.split("=", 1)[1].strip()
            if current_id and re.fullmatch(r"[0-9a-fA-F]{64}", value):
                keys[current_id] = Ed25519PublicKey.from_public_bytes(bytes.fromhex(value))
            continue
        if line == _PEM_BEGIN:
            in_pem = True
            pem_lines = [line]
            continue
        if in_pem:
            pem_lines.append(raw_line)
            if line == _PEM_END:
                in_pem = False
                if current_id:
                    try:
                        key = load_pem_public_key("\n".join(pem_lines).encode("utf-8"))
                    except ValueError:
                        key = None
                    if isinstance(key, Ed25519PublicKey):
                        keys[current_id] = key
                pem_lines = []

    if not keys:
        raise MarketplaceError(
            "marketplace_signature_invalid",
            "内置市场公钥表为空",
            {"reason": "public_key_invalid"},
        )
    return keys


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_private_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _validate_fetch_url(url: str, *, redirected: bool) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme == "file" and not redirected:
        return url
    if scheme == "https":
        if redirected and _is_private_host(parsed.hostname or ""):
            raise MarketplaceError(
                "marketplace_fetch_failed", "索引重定向到私网地址", {"reason": "private_redirect"}
            )
        return url
    if scheme == "http" and _is_loopback_host(parsed.hostname or ""):
        return url
    raise MarketplaceError(
        "marketplace_fetch_failed",
        "索引地址必须是 https、localhost 或 file",
        {"reason": "url_rejected"},
    )


def path_from_file_url(url: str) -> Path:
    return Path(url2pathname(urlsplit(url).path))


def _client(factory: ClientFactory | None) -> httpx.Client:
    if factory is not None:
        return factory()
    return httpx.Client(timeout=httpx.Timeout(FETCH_TIMEOUT_S))


def _http_get_bytes(url: str, factory: ClientFactory | None) -> bytes:
    current = url
    with _client(factory) as client:
        for attempt in range(MAX_REDIRECTS + 1):
            current = _validate_fetch_url(current, redirected=attempt > 0)
            try:
                response = client.get(current, follow_redirects=False)
            except httpx.HTTPError as exc:
                raise MarketplaceError(
                    "marketplace_fetch_failed", "无法连接市场索引", {"reason": type(exc).__name__}
                ) from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise MarketplaceError(
                        "marketplace_fetch_failed", "索引重定向缺少 Location", {"status": 302}
                    )
                current = str(response.url.join(location))
                if attempt == MAX_REDIRECTS:
                    break
                continue
            if response.status_code >= 400:
                raise MarketplaceError(
                    "marketplace_fetch_failed",
                    "市场索引返回错误",
                    {"status": response.status_code},
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_INDEX_BYTES:
                raise MarketplaceError(
                    "marketplace_resource_exceeded",
                    "市场索引超过大小上限",
                    {"maxBytes": MAX_INDEX_BYTES},
                )
            body = response.content
            if len(body) > MAX_INDEX_BYTES:
                raise MarketplaceError(
                    "marketplace_resource_exceeded",
                    "市场索引超过大小上限",
                    {"maxBytes": MAX_INDEX_BYTES},
                )
            return body
    raise MarketplaceError(
        "marketplace_fetch_failed", "索引重定向次数过多", {"maxRedirects": MAX_REDIRECTS}
    )


def fetch_raw_index(url: str, *, client_factory: ClientFactory | None = None) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme.lower() == "file":
        path = path_from_file_url(url)
        if not path.is_file():
            raise MarketplaceError(
                "marketplace_not_configured", "市场索引尚未构建", {"source": "file"}
            )
        if path.stat().st_size > MAX_INDEX_BYTES:
            raise MarketplaceError(
                "marketplace_resource_exceeded",
                "市场索引超过大小上限",
                {"maxBytes": MAX_INDEX_BYTES},
            )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise MarketplaceError(
                "marketplace_fetch_failed", "无法读取市场索引文件", {"reason": "io_error"}
            ) from exc
    return _http_get_bytes(url, client_factory)


def _validate_file_field(entry: MarketplaceEntry) -> None:
    value = entry.file
    if not value or len(value) > 512:
        raise MarketplaceError(
            "marketplace_index_invalid", "模块包的 file 字段无效", {"id": entry.id}
        )
    if any(ch in value for ch in ("\\", "\x00", "\r", "\n")):
        raise MarketplaceError(
            "marketplace_index_invalid", "模块包路径包含非法字符", {"id": entry.id}
        )
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme.lower() not in ("http", "https", "file"):
            raise MarketplaceError(
                "marketplace_index_invalid", "模块包地址协议不受支持", {"id": entry.id}
            )
        if any(part == ".." for part in Path(parsed.path).parts):
            raise MarketplaceError(
                "marketplace_index_invalid", "模块包路径包含 ..", {"id": entry.id}
            )
        return
    if value.startswith("/") or any(part == ".." for part in Path(value).parts):
        raise MarketplaceError(
            "marketplace_index_invalid", "模块包路径必须是索引目录内的相对路径", {"id": entry.id}
        )
    if not value.lower().endswith(".ehmod"):
        raise MarketplaceError(
            "marketplace_index_invalid", "模块包必须是 .ehmod", {"id": entry.id}
        )


def _validate_entries(index: MarketplaceIndex) -> None:
    seen: set[tuple[str, str]] = set()
    for entry in index.modules:
        if not ID_RE.match(entry.id):
            raise MarketplaceError(
                "marketplace_index_invalid", "模块 id 不合法", {"id": entry.id[:64]}
            )
        if parse_version(entry.version) is None:
            raise MarketplaceError(
                "marketplace_index_invalid",
                "模块版本不是合法 SemVer",
                {"id": entry.id, "version": entry.version[:64]},
            )
        if parse_version(entry.min_core_version) is None:
            raise MarketplaceError(
                "marketplace_index_invalid",
                "minCoreVersion 不是合法 SemVer",
                {"id": entry.id, "minCoreVersion": entry.min_core_version[:64]},
            )
        if not SHA256_RE.match(entry.sha256):
            raise MarketplaceError(
                "marketplace_index_invalid", "sha256 必须是 64 位小写十六进制", {"id": entry.id}
            )
        if entry.size <= 0 or entry.size > MAX_DOWNLOAD_BYTES:
            raise MarketplaceError(
                "marketplace_index_invalid",
                "模块包大小超出允许范围",
                {"id": entry.id, "maxBytes": MAX_DOWNLOAD_BYTES},
            )
        key = (entry.id, entry.version)
        if key in seen:
            raise MarketplaceError(
                "marketplace_index_invalid",
                "索引中模块版本重复",
                {"id": entry.id, "version": entry.version[:64]},
            )
        seen.add(key)
        _validate_file_field(entry)


def verify_and_validate(
    raw: Any,
    *,
    expected_source: str | None,
    public_key_path: Path,
) -> MarketplaceIndex:
    """先验签、后建模；验签失败时绝不返回未验签数据。"""
    if not isinstance(raw, dict):
        raise MarketplaceError("marketplace_index_invalid", "索引顶层必须是对象")
    if str(raw.get("schemaVersion")) != "1":
        raise MarketplaceError(
            "marketplace_index_invalid", "不支持的索引 schemaVersion", {"expected": "1"}
        )
    source = str(raw.get("source") or "")
    if source not in ("official", "community"):
        raise MarketplaceError("marketplace_index_invalid", "索引 source 无效")
    if expected_source is not None and source != expected_source:
        raise MarketplaceError(
            "marketplace_index_invalid",
            "索引 source 与请求的市场源不一致",
            {"expected": expected_source},
        )
    key_id = raw.get("keyId")
    if not isinstance(key_id, str) or not KEY_ID_RE.match(key_id):
        raise MarketplaceError("marketplace_index_invalid", "索引缺少合法 keyId")
    signature = raw.get("signature")
    if not isinstance(signature, str) or not signature:
        raise MarketplaceError(
            "marketplace_signature_invalid", "索引未签名", {"keyId": key_id}
        )
    keys = load_public_keys(public_key_path)
    key = keys.get(key_id)
    if key is None:
        raise MarketplaceError(
            "marketplace_signature_invalid", "索引 keyId 没有对应公钥", {"keyId": key_id}
        )
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MarketplaceError(
            "marketplace_signature_invalid", "签名不是合法 base64", {"keyId": key_id}
        ) from exc
    body = {key_name: value for key_name, value in raw.items() if key_name != "signature"}
    try:
        key.verify(signature_bytes, canonical_bytes(body))
    except InvalidSignature as exc:
        raise MarketplaceError(
            "marketplace_signature_invalid", "索引签名校验失败", {"keyId": key_id}
        ) from exc

    try:
        index = MarketplaceIndex.model_validate(raw)
    except PydanticValidationError as exc:
        raise MarketplaceError(
            "marketplace_index_invalid",
            "索引条目不符合格式",
            {"errors": [
                {"path": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
                for error in exc.errors()[:8]
            ]},
        ) from exc

    if source == "community":
        # 社区索引永远不能声称已验证；verified 只是官方索引的语义。
        for entry in index.modules:
            entry.verified = False
    _validate_entries(index)
    return index


def fetch_index(
    source: str,
    config: MarketplaceConfig | None = None,
    *,
    client_factory: ClientFactory | None = None,
) -> MarketplaceIndex:
    source = validate_source(source)
    resolved = config or MarketplaceConfig.from_env()
    url = resolved.url_for(source)
    if not url:
        raise MarketplaceError(
            "marketplace_not_configured", "市场源未配置", {"source": source}
        )
    cache_key = f"{source}\0{url}\0{resolved.public_key_path}"
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

    body = fetch_raw_index(url, client_factory=client_factory)
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketplaceError(
            "marketplace_index_invalid", "索引不是合法 UTF-8 JSON"
        ) from exc
    index = verify_and_validate(
        raw, expected_source=source, public_key_path=resolved.public_key_path
    )
    with _cache_lock:
        _cache[cache_key] = (now + CACHE_TTL_S, index)
    return index


def select_entry(index: MarketplaceIndex, module_id: str, version: str | None) -> MarketplaceEntry:
    """版本为空时取该模块的最高版本；否则必须精确匹配。"""
    candidates = [entry for entry in index.modules if entry.id == module_id]
    if not candidates:
        raise MarketplaceError(
            "marketplace_module_not_found", "索引中没有该模块", {"moduleId": module_id[:128]}
        )
    if version is not None:
        for entry in candidates:
            if entry.version == version:
                return entry
        raise MarketplaceError(
            "marketplace_module_not_found",
            "索引中没有该版本",
            {"moduleId": module_id[:128], "version": version[:64]},
        )
    return max(candidates, key=lambda item: parse_version(item.version) or Version(0, 0, 0))


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()

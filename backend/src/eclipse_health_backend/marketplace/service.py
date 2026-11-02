"""市场安装与更新检查：下载、校验后交给现有 ``ModuleManager.install``。"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

import httpx

from ..modules.constants import CORE_VERSION
from ..modules.semver import parse_version
from .config import PROJECT_ROOT, MarketplaceConfig
from .errors import MarketplaceError, validate_source
from .index import (
    MAX_DOWNLOAD_BYTES,
    MAX_REDIRECTS,
    ClientFactory,
    _is_loopback_host,
    _is_private_host,
    fetch_index,
    path_from_file_url,
    select_entry,
)
from .models import MarketplaceEntry, MarketplaceIndex

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024
# 模块包可能几十 MB，GitHub Pages 在国内经常 >15 秒才传完；读超时给足 5 分钟。
_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)
_DOWNLOAD_ATTEMPTS = 3


class MarketplaceService:
    """一次请求内的市场服务；索引缓存跨请求共享。"""

    def __init__(
        self,
        manager: Any,
        *,
        config: MarketplaceConfig | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.manager = manager
        self._config = config
        self._client_factory = client_factory

    # ------------------------------------------------------------------ 公共接口
    def list_entries(
        self,
        source: str,
        *,
        query: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        source = validate_source(source)
        index = fetch_index(source, self._config)
        modules = list(index.modules)
        if query:
            needle = query.strip().lower()
            modules = [
                entry
                for entry in modules
                if needle
                in " ".join(
                    [
                        entry.id,
                        entry.name,
                        entry.description,
                        entry.author,
                        *(entry.categories or []),
                    ]
                ).lower()
            ]
        if category:
            wanted = category.strip().lower()
            modules = [
                entry
                for entry in modules
                if any(item.lower() == wanted for item in entry.categories)
            ]
        modules.sort(key=lambda entry: (entry.id, entry.version))
        return {
            "schemaVersion": index.schema_version,
            "source": index.source,
            "generatedAt": index.generated_at,
            "keyId": index.key_id,
            "modules": [entry.model_dump(by_alias=True) for entry in modules],
            "count": len(modules),
        }

    def updates(self) -> dict[str, Any]:
        config = self._config or MarketplaceConfig.from_env()
        installed = {item["id"]: item for item in self.manager.list_modules()}
        updates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source in ("official", "community"):
            try:
                index = fetch_index(source, config)
            except MarketplaceError as exc:
                if exc.code == "marketplace_not_configured":
                    continue
                raise
            latest: dict[str, MarketplaceEntry] = {}
            for entry in index.modules:
                current = latest.get(entry.id)
                parsed = parse_version(entry.version)
                if parsed is None:
                    continue
                if current is None or parsed > (parse_version(current.version) or parsed):
                    latest[entry.id] = entry
            for module_id, entry in latest.items():
                if module_id in seen:
                    # 官方索引优先；社区索引只补充官方没有的模块。
                    continue
                seen.add(module_id)
                installed_item = installed.get(module_id)
                if installed_item is None:
                    continue
                installed_version = parse_version(str(installed_item.get("version", "")))
                latest_version = parse_version(entry.version)
                if installed_version is None or latest_version is None:
                    continue
                if latest_version > installed_version:
                    updates.append(
                        {
                            "moduleId": module_id,
                            "name": entry.name,
                            "installedVersion": str(installed_item.get("version", "")),
                            "latestVersion": entry.version,
                            "source": source,
                            "verified": entry.verified,
                            "size": entry.size,
                            "sha256": entry.sha256,
                            "file": entry.file,
                        }
                    )
        updates.sort(key=lambda item: item["moduleId"])
        return {"updates": updates, "count": len(updates)}

    def install(
        self,
        source: str,
        module_id: str,
        version: str | None = None,
        *,
        enable: bool = False,
    ) -> dict[str, Any]:
        source = validate_source(source)
        config = self._config or MarketplaceConfig.from_env()
        index = fetch_index(source, config)
        entry = select_entry(index, module_id, version)
        self._require_core_version(entry)
        index_url = config.url_for(source) or ""

        try:
            with self._downloaded_archive(entry, index_url) as archive:
                summary = self.manager.install(archive, enable=enable)
        except MarketplaceError as exc:
            self._audit(entry, index, source, ok=False, error_code=exc.code)
            raise
        except Exception as exc:
            self._audit(
                entry, index, source, ok=False, error_code=getattr(exc, "code", type(exc).__name__)
            )
            raise

        self._audit(entry, index, source, ok=True)
        payload: dict[str, Any] = {
            "source": source,
            "moduleId": entry.id,
            "version": entry.version,
            "keyId": index.key_id,
            "verified": entry.verified,
            "sha256": entry.sha256,
            "size": entry.size,
            "module": summary,
        }
        # 同时摊平内核摘要字段（id/name/enabled/...），方便 UI 直接复用模块安装响应。
        if isinstance(summary, dict):
            for name, value in summary.items():
                payload.setdefault(name, value)
        return payload

    # ------------------------------------------------------------------ 下载与校验
    @staticmethod
    def _require_core_version(entry: MarketplaceEntry) -> None:
        core = parse_version(CORE_VERSION)
        required = parse_version(entry.min_core_version)
        if core is not None and required is not None and core < required:
            raise MarketplaceError(
                "marketplace_incompatible_core",
                "该模块要求更高版本的核心",
                {
                    "moduleId": entry.id,
                    "minCoreVersion": entry.min_core_version,
                    "coreVersion": CORE_VERSION,
                },
            )

    @contextmanager
    def _downloaded_archive(self, entry: MarketplaceEntry, index_url: str) -> Iterator[Path]:
        directory = Path(tempfile.mkdtemp(prefix="eh-marketplace-"))
        try:
            archive = directory / f"{entry.id}-{entry.version}.ehmod"
            self._download_to(entry, index_url, archive)
            self._verify_archive(archive, entry)
            yield archive
        finally:
            # 无论安装成功、sha256 失败还是 manager 抛错，都不留下临时包。
            shutil.rmtree(directory, ignore_errors=True)

    def _download_to(self, entry: MarketplaceEntry, index_url: str, destination: Path) -> None:
        url = self._resolve_download_url(index_url, entry.file)
        parsed = urlsplit(url)
        if parsed.scheme.lower() == "file":
            source_path = Path(url2pathname(parsed.path))
            self._copy_local(entry, source_path, destination)
            return
        # 随包已带同名 .ehmod 时优先本地拷贝：安装包内置 32 个模块，
        # 不必再走 GitHub Pages（国内几十 MB 经常超时）。
        bundled = self._bundled_package(entry)
        if bundled is not None:
            self._copy_local(entry, bundled, destination)
            return
        self._download_http(entry, url, destination)

    @staticmethod
    def _bundled_package(entry: MarketplaceEntry) -> Path | None:
        name = Path(entry.file).name
        candidates = [
            Path(__file__).resolve().parent / "packages" / name,
            PROJECT_ROOT / "dist" / "modules" / name,
        ]
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size == entry.size:
                    return candidate
            except OSError:
                continue
        return None

    def _resolve_download_url(self, index_url: str, file_value: str) -> str:
        if urlsplit(file_value).scheme:
            self._check_download_url(file_value, redirected=False)
            return file_value
        index_parsed = urlsplit(index_url)
        resolved = urljoin(index_url, file_value)
        if index_parsed.scheme.lower() == "file":
            index_path = path_from_file_url(index_url)
            candidates = [
                index_path.parent / file_value,
                index_path.parent.parent / file_value,
                # 开发用：索引只提交 JSON，.ehmod 由 pack_official_modules.py 放在 dist/。
                PROJECT_ROOT / "dist" / "modules" / Path(file_value).name,
                # 打包后：.ehmod 随 sidecar 放在 marketplace/packages/。
                Path(__file__).resolve().parent / "packages" / Path(file_value).name,
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate.as_uri()
        return resolved

    def _copy_local(self, entry: MarketplaceEntry, source: Path, destination: Path) -> None:
        if not source.is_file():
            raise MarketplaceError(
                "marketplace_download_failed", "模块包文件不存在", {"moduleId": entry.id}
            )
        size = source.stat().st_size
        if size > MAX_DOWNLOAD_BYTES:
            raise MarketplaceError(
                "marketplace_resource_exceeded",
                "模块包超过大小上限",
                {"maxBytes": MAX_DOWNLOAD_BYTES},
            )
        digest = hashlib.sha256()
        written = 0
        try:
            with source.open("rb") as reader, destination.open("wb") as writer:
                while chunk := reader.read(_CHUNK):
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise MarketplaceError(
                            "marketplace_resource_exceeded",
                            "模块包超过大小上限",
                            {"maxBytes": MAX_DOWNLOAD_BYTES},
                        )
                    digest.update(chunk)
                    writer.write(chunk)
        except OSError as exc:
            raise MarketplaceError(
                "marketplace_download_failed", "无法读取模块包", {"moduleId": entry.id}
            ) from exc
        self._check_integrity(entry, written, digest.hexdigest())

    def _download_http(self, entry: MarketplaceEntry, url: str, destination: Path) -> None:
        factory = self._client_factory
        client = factory() if factory is not None else httpx.Client(timeout=_DOWNLOAD_TIMEOUT)
        current = url
        last_error: httpx.HTTPError | None = None
        with client:
            for attempt in range(_DOWNLOAD_ATTEMPTS):
                try:
                    self._fetch_once(entry, current, destination, client)
                    return
                except httpx.HTTPError as exc:
                    last_error = exc
                    destination.unlink(missing_ok=True)
                    if attempt + 1 < _DOWNLOAD_ATTEMPTS:
                        logger.warning(
                            "marketplace download retry %s/%s module=%s reason=%s",
                            attempt + 1,
                            _DOWNLOAD_ATTEMPTS,
                            entry.id,
                            type(exc).__name__,
                        )
                        time.sleep(1.5 * (attempt + 1))
        raise MarketplaceError(
            "marketplace_download_failed",
            "无法连接模块包地址",
            {
                "reason": type(last_error).__name__ if last_error else "unknown",
                "attempts": _DOWNLOAD_ATTEMPTS,
            },
        )

    def _fetch_once(
        self,
        entry: MarketplaceEntry,
        url: str,
        destination: Path,
        client: httpx.Client,
    ) -> None:
        current = url
        for attempt in range(MAX_REDIRECTS + 1):
            self._check_download_url(current, redirected=attempt > 0)
            with client.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise MarketplaceError(
                            "marketplace_download_failed", "下载重定向缺少 Location"
                        )
                    current = str(response.url.join(location))
                    if attempt == MAX_REDIRECTS:
                        break
                    continue
                if response.status_code >= 500:
                    # 交给外层重试。
                    raise httpx.HTTPStatusError(
                        f"server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 400:
                    raise MarketplaceError(
                        "marketplace_download_failed",
                        "模块包下载返回错误",
                        {"status": response.status_code},
                    )
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
                    raise MarketplaceError(
                        "marketplace_resource_exceeded",
                        "模块包超过大小上限",
                        {"maxBytes": MAX_DOWNLOAD_BYTES},
                    )
                self._write_stream(response, destination, entry)
                return
        raise MarketplaceError(
            "marketplace_download_failed",
            "模块包重定向次数过多",
            {"maxRedirects": MAX_REDIRECTS},
        )

    def _write_stream(
        self, response: httpx.Response, destination: Path, entry: MarketplaceEntry
    ) -> None:
        digest = hashlib.sha256()
        written = 0
        try:
            with destination.open("wb") as writer:
                for chunk in response.iter_bytes(_CHUNK):
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise MarketplaceError(
                            "marketplace_resource_exceeded",
                            "模块包超过大小上限",
                            {"maxBytes": MAX_DOWNLOAD_BYTES},
                        )
                    digest.update(chunk)
                    writer.write(chunk)
        except OSError as exc:
            raise MarketplaceError(
                "marketplace_download_failed", "无法写入模块包", {"moduleId": entry.id}
            ) from exc
        self._check_integrity(entry, written, digest.hexdigest())

    @staticmethod
    def _check_integrity(entry: MarketplaceEntry, size: int, sha256: str) -> None:
        if size != entry.size:
            raise MarketplaceError(
                "marketplace_checksum_mismatch",
                "模块包大小与索引不一致",
                {"moduleId": entry.id, "expected": entry.size, "actual": size},
            )
        if sha256 != entry.sha256:
            raise MarketplaceError(
                "marketplace_checksum_mismatch",
                "模块包 sha256 与索引不一致",
                {"moduleId": entry.id, "expected": entry.sha256, "actual": sha256},
            )

    def _verify_archive(self, archive: Path, entry: MarketplaceEntry) -> None:
        size = archive.stat().st_size
        digest = hashlib.sha256()
        with archive.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
        self._check_integrity(entry, size, digest.hexdigest())

    @staticmethod
    def _check_download_url(url: str, *, redirected: bool) -> None:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        if scheme == "file":
            if redirected:
                raise MarketplaceError(
                    "marketplace_download_url_rejected", "拒绝重定向到本地文件"
                )
            return
        if scheme == "https":
            if redirected and _is_private_host(host):
                raise MarketplaceError(
                    "marketplace_download_url_rejected", "拒绝重定向到私网地址"
                )
            return
        if scheme == "http" and _is_loopback_host(host):
            return
        raise MarketplaceError(
            "marketplace_download_url_rejected",
            "模块包地址必须是 https、localhost 或 file",
            {"reason": "url_rejected"},
        )

    # ------------------------------------------------------------------ 审计
    def _audit(
        self,
        entry: MarketplaceEntry,
        index: MarketplaceIndex,
        source: str,
        *,
        ok: bool,
        error_code: str | None = None,
    ) -> None:
        engine = getattr(self.manager, "engine", None)
        if engine is None:
            return
        from sqlalchemy.orm import Session as OrmSession

        from ..modules import audit as module_audit

        detail: dict[str, Any] = {
            "source": source,
            "keyId": index.key_id,
            "version": entry.version,
            "sha256": entry.sha256,
            "ok": ok,
        }
        if error_code:
            detail["errorCode"] = error_code
        try:
            with OrmSession(engine) as session:
                module_audit.append(
                    session, "marketplace.install", module_id=entry.id, detail=detail
                )
                session.commit()
        except Exception:
            logger.warning("marketplace audit write failed", exc_info=True)

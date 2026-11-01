"""Manifest 加载与校验：JSON Schema 2020-12 为事实源，Pydantic 只做类型化读取。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from .constants import (
    CORE_API_MAJOR,
    CORE_API_MINOR,
    CORE_API_VERSION,
    CORE_VERSION,
    MAX_MANIFEST_BYTES,
    SUPPORTED_SCHEMA_VERSIONS,
)
from .errors import ModuleError
from .semver import parse_version, satisfies

_SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"


class ModuleType(StrEnum):
    DEVICE_ADAPTER = "device-adapter"
    SIGNAL_ENGINE = "signal-engine"
    ANALYSIS_MODEL = "analysis-model"
    HEALTH_DOMAIN = "health-domain"
    DASHBOARD_WIDGET = "dashboard-widget"
    EXPORTER = "exporter"
    AI_TOOL = "ai-tool"
    THEME = "theme"
    LOCALE = "locale"
    DATA_SOURCE = "data-source"


class Permission(StrEnum):
    RECORDS_READ = "records:read"
    RECORDS_WRITE = "records:write"
    RECORDS_DELETE = "records:delete"
    FILES_USER_SELECTED = "files:user-selected"
    FILES_EXPORT = "files:export"
    NETWORK = "network"
    LLM = "llm"
    MODELS_DOWNLOAD = "models:download"
    UI_CUSTOM = "ui:custom"
    SYSTEM_NOTIFY = "system:notify"
    SYSTEM_BACKGROUND = "system:background"


ALL_PERMISSIONS: tuple[str, ...] = tuple(permission.value for permission in Permission)

MAX_DEPENDENCIES = 32
_MAX_DEPENDENCY_LENGTH = 200

# PEP 508 需求的一个受限子集：名称、extras、版本约束（可逗号分隔）与环境标记。
# 故意不接受 `name @ url`、`file:`、绝对/相对路径与 `-e`，依赖只能来自包索引。
_DEPENDENCY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
    r"(?:\s*\[[A-Za-z0-9._,-]+\])?"
    r"(?:\s*(?:===|==|!=|~=|<=|>=|<|>)\s*[A-Za-z0-9*][A-Za-z0-9.*+!_-]*"
    r"(?:\s*,\s*(?:===|==|!=|~=|<=|>=|<|>)\s*[A-Za-z0-9*][A-Za-z0-9.*+!_-]*)*)?"
    r"(?:\s*;\s*[A-Za-z0-9._\s<>=!()\"',+-]+)?$"
)
# 正则本身已排除这些字符；单独检查是为了给出可读的错误原因。
_DEPENDENCY_FORBIDDEN_RE = re.compile(r"://|@|\\|:|(?:^|[\s,;(])(?:-e\b|/|\.{1,2}[/\\])")


def normalize_dependency(spec: str) -> str:
    """返回去除首尾空白后的 PEP 508 字符串；非法形式抛 ValueError。"""
    if not isinstance(spec, str):
        raise TypeError("依赖必须是 PEP 508 字符串")
    text = spec.strip()
    if not text:
        raise ValueError("依赖不能为空字符串")
    if len(text) > _MAX_DEPENDENCY_LENGTH:
        raise ValueError("依赖字符串超过 200 字符")
    if _DEPENDENCY_FORBIDDEN_RE.search(text):
        raise ValueError(f"依赖不允许 URL、本地路径或 -e 形式：{text[:80]}")
    if _DEPENDENCY_RE.match(text) is None:
        raise ValueError(f"依赖不是合法的 PEP 508 需求：{text[:80]}")
    return text


def validate_dependencies(items: Iterable[str]) -> tuple[str, ...]:
    """规范化并校验依赖列表：≤32 项、无重复、每项为合法 PEP 508。"""
    try:
        values = list(items)
    except TypeError as exc:
        raise ValueError("dependencies 必须是字符串数组") from exc
    if len(values) > MAX_DEPENDENCIES:
        raise ValueError(f"dependencies 最多 {MAX_DEPENDENCIES} 项")
    normalized = tuple(normalize_dependency(item) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError("dependencies 不能包含重复项")
    return normalized


def _schema_path() -> Path:
    candidates = [
        _SCHEMA_ROOT / "module.schema.json",
        Path(__file__).resolve().parent / "module.schema.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ModuleError("INVALID_PACKAGE", "模块 manifest schema 缺失，无法校验")


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    with _schema_path().open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _format_path(parts: list[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _readable_error(error: ValidationError) -> dict[str, str]:
    return {
        "path": _format_path(list(error.absolute_path)),
        "message": error.message,
    }


class ManifestAuthor(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    url: str | None = None
    email: str | None = None


class ManifestEngines(BaseModel):
    eclipse: str


class ManifestEntry(BaseModel):
    python: str
    factory: str


class ManifestResources(BaseModel):
    memoryMb: int | None = None
    cpu: float | None = None
    startupTimeoutMs: int | None = None


class Manifest(BaseModel):
    """核心关心的字段；contributes 保留原始结构供各类型自行解释。"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    schema_version: str = Field(alias="schemaVersion")
    id: str
    name: str
    description: str
    version: str
    api_version: str = Field(alias="apiVersion")
    engines: ManifestEngines
    type: ModuleType
    author: ManifestAuthor
    license: str
    homepage: str | None = None
    repository: str | None = None
    permissions: list[str] = Field(default_factory=list)
    dependencies: tuple[str, ...] = ()
    allowed_hosts: list[str] = Field(default_factory=list, alias="allowedHosts")
    entry: ManifestEntry
    contributes: dict[str, Any] = Field(default_factory=dict)
    resources: ManifestResources = Field(default_factory=ManifestResources)
    update_channel: str | None = Field(default=None, alias="updateChannel")
    i18n: dict[str, str] = Field(default_factory=dict)

    @field_validator("dependencies")
    @classmethod
    def _check_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # schema 已拦截同类问题；这里保证程序内直接构造 Manifest 时也安全。
        return validate_dependencies(value)

    @property
    def entry_path(self) -> str:
        return self.entry.python

    @property
    def startup_timeout_s(self) -> float:
        millis = self.resources.startupTimeoutMs or 10000
        return max(0.5, millis / 1000.0)

    def contribution_ids(self) -> list[str]:
        ids: list[str] = []
        for key, value in self.contributes.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("id"), str):
                        ids.append(f"{key}:{item['id']}")
        return ids


def parse_manifest(data: dict[str, Any]) -> Manifest:
    errors = sorted(_validator().iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        raise ModuleError(
            "INVALID_INPUT",
            "module.json 不符合 module.schema.json",
            {"errors": [_readable_error(error) for error in errors]},
        )
    try:
        return Manifest.model_validate(data)
    except PydanticValidationError as exc:  # 理论上 schema 已拦截，兜底给可读错误。
        errors = [
            {"path": "$." + ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        raise ModuleError("INVALID_INPUT", "module.json 字段无法解析", {"errors": errors}) from exc


def load_manifest_file(path: Path) -> Manifest:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ModuleError("INVALID_PACKAGE", "module.json 无法读取") from exc
    if size > MAX_MANIFEST_BYTES:
        raise ModuleError("INVALID_PACKAGE", "module.json 超过 1MB 上限")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModuleError("INVALID_PACKAGE", "module.json 不是合法 UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ModuleError("INVALID_PACKAGE", "module.json 顶层必须是对象")
    return parse_manifest(raw)


def check_compatibility(
    manifest: Manifest,
    core_version: str = CORE_VERSION,
    core_api_major: int = CORE_API_MAJOR,
    core_api_minor: int = CORE_API_MINOR,
) -> None:
    """契约 §10：manifest/contract 版本与核心兼容。"""
    if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ModuleError(
            "INCOMPATIBLE_API",
            f"manifest schemaVersion {manifest.schema_version} 不受支持",
            {"supported": sorted(SUPPORTED_SCHEMA_VERSIONS)},
        )
    api = parse_version(f"{manifest.api_version}.0")
    if api is None:
        raise ModuleError("INCOMPATIBLE_API", f"apiVersion {manifest.api_version} 不是合法版本")
    if api.major != core_api_major or api.minor > core_api_minor:
        raise ModuleError(
            "INCOMPATIBLE_API",
            f"模块要求 apiVersion {manifest.api_version}，核心为 {CORE_API_VERSION}",
            {"module": manifest.api_version, "core": CORE_API_VERSION},
        )
    if not satisfies(core_version, manifest.engines.eclipse):
        raise ModuleError(
            "INCOMPATIBLE_API",
            f"模块要求核心版本 {manifest.engines.eclipse}，当前为 {core_version}",
            {"module": manifest.engines.eclipse, "core": core_version},
        )

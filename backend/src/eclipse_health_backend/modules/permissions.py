"""权限规则：契约 §6 的 scope 与「worker 回调核心方法」所需权限的映射。"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ModuleError
from .manifest import ALL_PERMISSIONS

# 模块 -> 核心 的受限 RPC 所需 scope；None 表示不需要额外权限。
CORE_RPC_SCOPES: dict[str, str | None] = {
    "records.query": "records:read",
    "records.get": "records:read",
    "records.create": "records:write",
    "records.update": "records:write",
    "records.delete": "records:delete",
    "signals.read": "records:read",
    "files.pick": "files:user-selected",
    "files.export": "files:export",
    "models.download": "models:download",
    "models.load": None,
    "llm.complete": "llm",
    "events.emit": None,
    "log.write": None,
    "audit.write": None,
}


# 契约 §6：records:delete 属高风险权限，默认不授予，需要用户显式开启。
DEFAULT_DENIED_SCOPES: frozenset[str] = frozenset({"records:delete"})


# UI 需要把权限按风险分级展示；本表只描述，不参与授权判断。
HIGH_RISK_SCOPES: frozenset[str] = frozenset(
    {"records:delete", "network", "ui:custom"}
)


@dataclass(frozen=True, slots=True)
class PermissionMeta:
    scope: str
    risk: str
    label: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "risk": self.risk,
            "label": self.label,
            "description": self.description,
        }


PERMISSION_META: dict[str, PermissionMeta] = {
    meta.scope: meta
    for meta in (
        PermissionMeta(
            "records:read",
            "low",
            "Read records",
            "Read records, measurements and analyses",
        ),
        PermissionMeta("records:write", "medium", "Write records", "Create and update records"),
        PermissionMeta(
            "records:delete",
            "high",
            "Delete records",
            "Delete records permanently; denied unless explicitly granted",
        ),
        PermissionMeta(
            "files:user-selected",
            "low",
            "Read selected files",
            "Read files the user picks in a file dialog",
        ),
        PermissionMeta(
            "files:export",
            "medium",
            "Export files",
            "Write files into a directory the user confirms",
        ),
        PermissionMeta(
            "network",
            "high",
            "Network access",
            "Reach hosts declared in allowedHosts",
        ),
        PermissionMeta(
            "llm",
            "medium",
            "Call LLM",
            "Send data to the user-configured LLM",
        ),
        PermissionMeta(
            "models:download",
            "medium",
            "Download models",
            "Download model weights",
        ),
        PermissionMeta(
            "ui:custom",
            "high",
            "Custom UI",
            "Render a sandboxed custom interface",
        ),
        PermissionMeta(
            "system:notify",
            "low",
            "Notifications",
            "Show system notifications",
        ),
        PermissionMeta(
            "system:background",
            "medium",
            "Run in background",
            "Keep running while the window is minimized",
        ),
    )
}


def describe_scope(scope: str) -> dict[str, str]:
    meta = PERMISSION_META.get(scope)
    if meta is not None:
        return meta.to_dict()
    return {"scope": scope, "risk": "medium", "label": scope, "description": ""}


def permission_catalog() -> list[dict[str, str]]:
    """按 manifest schema 的顺序返回全部权限，供 UI/OpenAPI 消费者展示。"""
    return [describe_scope(scope) for scope in ALL_PERMISSIONS]


def validate_scope(scope: str) -> str:
    if scope not in ALL_PERMISSIONS:
        raise ModuleError(
            "INVALID_INPUT",
            f"未知权限 {scope[:64]}",
            {"allowed": list(ALL_PERMISSIONS)},
        )
    return scope


def required_scope(core_method: str) -> tuple[bool, str | None]:
    """返回 (是否为已知核心方法, 所需 scope)。"""
    if core_method not in CORE_RPC_SCOPES:
        return False, None
    return True, CORE_RPC_SCOPES[core_method]


def check_core_call(granted: set[str], core_method: str) -> None:
    known, scope = required_scope(core_method)
    if not known:
        raise ModuleError("METHOD_NOT_FOUND", "核心不支持该方法", {"method": core_method[:64]})
    if scope is not None and scope not in granted:
        raise ModuleError(
            "PERMISSION_DENIED",
            "模块未获得调用该核心方法所需的权限",
            {"scope": scope, "method": core_method[:64]},
        )


def diff_scopes(previous: set[str], requested: set[str]) -> tuple[list[str], list[str]]:
    """返回 (新增, 移除)。升级新增权限需重新确认（B2 UI），内核先不自动授予。"""
    return sorted(requested - previous), sorted(previous - requested)

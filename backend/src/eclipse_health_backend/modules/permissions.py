"""权限规则：契约 §6 的 scope 与「worker 回调核心方法」所需权限的映射。"""

from __future__ import annotations

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

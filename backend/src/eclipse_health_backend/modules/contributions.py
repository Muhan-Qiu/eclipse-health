"""贡献注册表：聚合已安装且启用模块的 `contributes`，供 UI 与工具调用消费。

只读注册表：不启动 worker、不调用 RPC，也不执行任何模块代码。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import registry
from .errors import ModuleError
from .manager import ModuleManager
from .manifest import Manifest, Permission

CONTRIBUTION_KINDS: tuple[str, ...] = ("widgets", "pages", "tools", "recordTypes")


def _module_meta(row: registry.InstalledModule, manifest: Manifest) -> dict[str, Any]:
    return {
        "moduleId": row.id,
        "moduleName": manifest.name,
        "moduleVersion": row.version,
        "moduleType": manifest.type.value,
    }


def _tag_items(
    items: Any, meta: dict[str, Any]
) -> list[dict[str, Any]]:
    """给每项贡献补上模块归属；模块字段覆盖同名贡献字段，避免伪造归属。"""
    if not isinstance(items, list):
        return []
    tagged: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            tagged.append({**item, **meta})
    return tagged


def _compile_tool(tool: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """统一工具形状：v2 允许 `parameters` 作为 `inputSchema` 的别名。"""
    input_schema = tool.get("inputSchema")
    if input_schema is None:
        input_schema = tool.get("parameters", {})
    compiled: dict[str, Any] = {
        **meta,
        "id": tool.get("id"),
        "name": tool.get("name"),
        "description": tool.get("description"),
        "inputSchema": input_schema,
    }
    for key in ("outputSchema", "longRunning", "permissions"):
        if key in tool:
            compiled[key] = tool[key]
    return compiled


def _manifest_of(row: registry.InstalledModule) -> Manifest | None:
    # 注册表只写入校验过的 manifest；解析失败说明库被外部改坏，跳过该行而不是让整页 500。
    try:
        return Manifest.model_validate(row.manifest())
    except ValidationError:
        return None


def collect_contributions(manager: ModuleManager, *, kind: str | None = None) -> dict[str, Any]:
    """聚合贡献点；`kind` 为 None 时返回四类分组。"""
    if kind is not None and kind not in CONTRIBUTION_KINDS:
        raise ModuleError(
            "INVALID_INPUT",
            "未知的贡献类型",
            {"type": kind[:32], "allowed": list(CONTRIBUTION_KINDS)},
        )

    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in CONTRIBUTION_KINDS}
    session = Session(manager.engine)
    try:
        for row in registry.list_installed(session):
            if not row.enabled:
                continue
            manifest = _manifest_of(row)
            if manifest is None:
                continue
            meta = _module_meta(row, manifest)
            contributes = manifest.contributes or {}
            ui = contributes.get("ui")
            ui = ui if isinstance(ui, dict) else {}
            groups["widgets"].extend(_tag_items(ui.get("widgets"), meta))
            groups["pages"].extend(_tag_items(ui.get("pages"), meta))
            groups["recordTypes"].extend(_tag_items(contributes.get("recordTypes"), meta))
            # 工具会经由 LLM 触达数据，只有在模块被授予 llm 后才对外可见。
            if Permission.LLM.value in registry.granted_scopes(session, row.id):
                for tool in contributes.get("tools") or []:
                    if isinstance(tool, dict):
                        groups["tools"].append(_compile_tool(tool, meta))
    finally:
        session.close()

    if kind is not None:
        return {"type": kind, "items": groups[kind]}
    return {**groups, "counts": {name: len(items) for name, items in groups.items()}}


__all__ = ["CONTRIBUTION_KINDS", "collect_contributions"]

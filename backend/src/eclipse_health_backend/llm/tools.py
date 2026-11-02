"""只读工具：把「最小可发送切片」暴露给模型。

硬约束：

- 只返回摘要 / 测量 / 质量 / 警告；**不返回波形、notes、成员姓名**；
- 记录与分析必须属于当前成员，否则按 ``NOT_FOUND`` 处理（不泄漏存在性）；
- 工具只读，任何写操作都不在这里。

``execute`` 返回统一结构，供 agent 同时生成 SSE 事件与透明面板摘要：

    {"ok": bool, "result": {...}, "summary": "...", "citations": [...]}
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from ..db import analysis_repo
from ..db.models import RecordTable
from ..db.repositories import get_record_row, list_signal_rows
from ..domain.common import to_storage_dt, utc_now
from ..domain.ids import uuid7

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_JSON = 12_000


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_records",
            "description": (
                "列出当前成员最近的 ECG 记录（只含摘要，不含波形与备注）。"
                "用于回答“我有几条记录/最近一次是什么时候”。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "返回条数，默认 5",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "按 ID 读取一条 ECG 记录的摘要（不含波形、备注与成员信息）。",
            "parameters": {
                "type": "object",
                "properties": {"recordId": {"type": "string"}},
                "required": ["recordId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analysis",
            "description": "按 ID 读取分析结果摘要：状态、摘要句、信号质量、警告与耗时。",
            "parameters": {
                "type": "object",
                "properties": {"analysisId": {"type": "string"}},
                "required": ["analysisId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_measurements",
            "description": (
                "读取一次分析的测量值（心率、HRV、QRS/QT、各类心搏比例）。"
                "回答数值问题时必须使用这个工具，不要凭记忆。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"analysisId": {"type": "string"}},
                "required": ["analysisId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trends",
            "description": (
                "读取当前成员若干测量码的历史趋势。用于“和上次比怎么样/最近趋势”。"
                "趋势能力未启用时返回 available=false。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 6,
                        "description": "测量码，如 heart_rate_mean、rmssd、sdnn",
                    },
                    "days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 365,
                        "description": "回看天数，默认 30",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_card",
            "description": "读取分析模型卡：模型版本、类别、局限与非诊断声明。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analysis_queue",
            "description": (
                "读取分析队列与引擎状态：是否暂停、当前运行的分析、已运行秒数、"
                "活跃分析进度、排队数和看门狗超时。用户说「分析卡住了/一直 40%」"
                "或需要诊断时先调用这个工具。"
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_analyses",
            "description": "列出某条记录的全部分析任务（状态、进度、错误、耗时）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "recordId": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["recordId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_analysis",
            "description": (
                "为当前成员的一条 ECG 记录发起分析。只有用户明确要求「开始分析/重新分析」"
                "时才调用；同一记录已有进行中任务时会复用它。force=true 会先取消旧任务"
                "再新建，用于卡死后的重新分析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recordId": {"type": "string"},
                    "engine": {"type": "string", "maxLength": 64},
                    "force": {
                        "type": "boolean",
                        "description": "取消该记录上仍在排队/运行的任务后重新发起",
                    },
                    "allowShortRecord": {
                        "type": "boolean",
                        "description": "允许少于 64 搏的短记录（零填充）",
                    },
                    "tailMode": {"type": "string", "enum": ["pad", "drop"]},
                },
                "required": ["recordId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_analysis",
            "description": (
                "取消一条分析。运行中的任务会中断分析引擎，让队列立即继续；"
                "只有用户明确要求停止/取消时才调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"analysisId": {"type": "string"}},
                "required": ["analysisId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_analysis",
            "description": "按原引擎与参数重试一条失败、取消或卡住的分析（先取消旧任务再新建）。",
            "parameters": {
                "type": "object",
                "properties": {"analysisId": {"type": "string"}},
                "required": ["analysisId"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_analysis_queue",
            "description": (
                "暂停领取新的分析任务；正在运行的任务不会被中断。"
                "用户要求「暂停分析队列」时调用。"
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume_analysis_queue",
            "description": "恢复分析队列，继续执行排队中的任务。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recover_stuck_analyses",
            "description": (
                "修复卡死的分析：把超时仍处于 queued/running 的任务标记为 interrupted，"
                "释放同记录的分析占用。用户反馈「删了/重开也不能分析」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "maxAgeSeconds": {
                        "type": "number",
                        "minimum": 0,
                        "description": "只修复超过该秒数的任务；省略时使用看门狗超时",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_card_templates",
            "description": (
                "列出内置的仪表盘卡片模板（压力、血氧、血压、运动、睡眠）。"
                "用户想添加健康数据卡片时先看这里。"
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dashboard_card",
            "description": (
                "根据健康数据类型生成一张仪表盘卡片草稿并返回预览。"
                "只创建草稿，不会直接保存；必须等用户明确同意后再调用 "
                "confirm_dashboard_card。不支持 SQL / JS / 模板表达式。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 80},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "steps",
                            "heart-rate",
                            "sleep",
                            "body-mass",
                            "blood-pressure",
                            "exercise",
                            "spo2",
                            "stress",
                            "glucose",
                        ],
                        "description": "健康数据类型",
                    },
                    "aggregation": {
                        "type": "string",
                        "enum": ["latest", "avg", "min", "max", "sum", "count"],
                    },
                    "windowDays": {"type": "integer", "minimum": 1, "maximum": 365},
                    "view": {
                        "type": "string",
                        "enum": ["stat", "sparkline", "line", "bar"],
                    },
                    "unit": {"type": "string", "maxLength": 16},
                    "colorToken": {
                        "type": "string",
                        "enum": [
                            "signal",
                            "accent",
                            "chart-1",
                            "chart-2",
                            "chart-3",
                            "chart-4",
                            "chart-5",
                        ],
                    },
                },
                "required": ["kind"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_dashboard_card",
            "description": (
                "用户明确确认后，把 create_dashboard_card 生成的草稿保存到仪表盘。"
                "draftId 必须来自 create_dashboard_card 的返回。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"draftId": {"type": "string"}},
                "required": ["draftId"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES = tuple(spec["function"]["name"] for spec in TOOL_SPECS)


# --------------------------------------------------------------------------- #
# 模块工具（B2）：已安装且授予 llm 的 ai-tool 模块，经模块 RPC 执行
# --------------------------------------------------------------------------- #

# 命名空间前缀让模型与前端都能一眼认出「这是第三方模块工具」。
MODULE_TOOL_PREFIX = "m_"
# `m_` + 8 位短哈希 + `_` = 11，剩余长度留给工具 id（provider 限制 64）。
MODULE_TOOL_SLUG_LIMIT = 53
# 模块结果对模型可见，但波形、备注与成员姓名一律不透传。
_BLOCKED_RESULT_KEYS = frozenset(
    {
        "samples",
        "signal",
        "signals",
        "waveform",
        "notes",
        "membername",
        "displayname",
        "beats",
    }
)
_MAX_RESULT_DEPTH = 8
_MAX_RESULT_ITEMS = 200
_MAX_RESULT_STRING = 2_000


def _fnv1a32(value: str) -> str:
    """短哈希：FNV-1a 32 位。

    前端用同样十行即可复现同一别名，无需把安装状态回传给 UI；
    不允许跨请求缓存安装状态，别名必须由模块身份纯函数决定。
    """
    digest = 0x811C9DC5
    for byte in value.encode("utf-8"):
        digest ^= byte
        digest = (digest * 0x01000193) & 0xFFFFFFFF
    return f"{digest:08x}"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", value).strip("_")
    return (cleaned or "tool")[:MODULE_TOOL_SLUG_LIMIT]


def module_tool_alias(module_id: str, tool_id: str) -> str:
    return f"{MODULE_TOOL_PREFIX}{_fnv1a32(module_id)}_{_slug(tool_id)}"


def _tighten_schema(value: Any) -> Any:
    """递归强制 `additionalProperties:false`，避免模型塞入模块没声明的参数。"""
    if isinstance(value, dict):
        tightened = {key: _tighten_schema(item) for key, item in value.items()}
        if tightened.get("type") == "object" or "properties" in tightened:
            tightened.setdefault("type", "object")
            tightened["additionalProperties"] = False
        return tightened
    if isinstance(value, list):
        return [_tighten_schema(item) for item in value]
    return value


def _tool_parameters(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        schema = {}
    tightened = _tighten_schema(schema)
    if tightened.get("type") != "object":
        # 函数调用的参数必须是对象；模块声明了别的顶层类型时退回空参数。
        return {"type": "object", "properties": {}, "additionalProperties": False}
    tightened.setdefault("properties", {})
    tightened["additionalProperties"] = False
    return tightened


@dataclass(frozen=True, slots=True)
class ModuleTool:
    """一条可调用的模块工具；别名是模型看到的唯一名字。"""

    alias: str
    module_id: str
    module_name: str
    tool_id: str
    tool_name: str
    description: str
    parameters: dict[str, Any]

    @property
    def display_name(self) -> str:
        return f"{self.module_name} · {self.tool_name}"

    def spec(self) -> dict[str, Any]:
        description = self.description or self.tool_name
        return {
            "type": "function",
            "function": {
                "name": self.alias,
                "description": f"[{self.module_name}] {description}",
                "parameters": self.parameters,
            },
        }


def module_tool_catalog(manager: Any | None = None) -> list[ModuleTool]:
    """读取贡献注册表（已过滤 enabled + llm）并编译为工具目录。

    每次调用都重新读库：安装、启用与授权随时可能变化，不做跨请求缓存。
    """
    try:
        from ..modules.api import get_manager
        from ..modules.contributions import collect_contributions

        payload = collect_contributions(manager or get_manager(), kind="tools")
    except Exception:  # 模块系统缺失时内置工具必须照常工作
        logger.warning("module tool catalog unavailable", exc_info=True)
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    tools: list[ModuleTool] = []
    claimed: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        module_id = item.get("moduleId")
        tool_id = item.get("id")
        if not isinstance(module_id, str) or not module_id:
            continue
        if not isinstance(tool_id, str) or not tool_id:
            continue
        alias = module_tool_alias(module_id, tool_id)
        if alias in claimed:
            # 64 位以内出现撞名时宁可少一个工具，也不让模型调用到另一个模块。
            logger.warning("module tool alias collision module=%s tool=%s", module_id, tool_id)
            continue
        claimed.add(alias)
        tools.append(
            ModuleTool(
                alias=alias,
                module_id=module_id,
                module_name=str(item.get("moduleName") or module_id),
                tool_id=tool_id,
                tool_name=str(item.get("name") or tool_id),
                description=str(item.get("description") or ""),
                parameters=_tool_parameters(item.get("inputSchema")),
            )
        )
    return tools


def _sanitize_module_result(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_RESULT_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): _sanitize_module_result(item, depth=depth + 1)
            for key, item in value.items()
            if str(key).lower() not in _BLOCKED_RESULT_KEYS
        }
    if isinstance(value, list):
        return [
            _sanitize_module_result(item, depth=depth + 1)
            for item in value[:_MAX_RESULT_ITEMS]
        ]
    if isinstance(value, str):
        return value[:_MAX_RESULT_STRING]
    return value


def trim_module_result(value: Any) -> dict[str, Any]:
    """裁剪模块返回值：先按字段脱敏，再按字节上限截断。"""
    sanitized = _sanitize_module_result(value)
    if not isinstance(sanitized, dict):
        sanitized = {"result": sanitized}
    text = json.dumps(sanitized, ensure_ascii=False, default=str)
    if len(text) <= MAX_TOOL_RESULT_JSON:
        return sanitized
    return {
        "truncated": True,
        "bytes": len(text),
        "note": "module tool result truncated",
        "preview": text[: MAX_TOOL_RESULT_JSON - 160],
    }


def _as_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _as_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolError("INVALID_ARGUMENT", f"{name} must be a non-empty string")
    return value.strip()


def _analysis_brief(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = row.data or {}
    quality = data.get("quality") or {}
    return {
        "id": row.id,
        "status": row.status,
        "summary": data.get("summary"),
        "qualityLevel": quality.get("level") if isinstance(quality, dict) else None,
        "qualityScore": quality.get("score") if isinstance(quality, dict) else None,
        "completedAt": data.get("completedAt"),
    }


class ToolBox:
    """绑定到「当前成员 + 当前 DB 会话」的一组只读工具。"""

    def __init__(
        self,
        session: Session,
        member_id: str,
        *,
        manager: Any | None = None,
    ) -> None:
        self._session = session
        self._member_id = member_id
        # 模块工具走独立内核；测试可显式注入，生产由 get_manager() 单例提供。
        self._manager = manager

    # ------------------------------------------------------------------ 入口
    def tool_specs(self) -> list[dict[str, Any]]:
        """内置工具 + 当前安装状态下的模块工具；每个对话轮次重建一次。"""
        return [*TOOL_SPECS, *(tool.spec() for tool in module_tool_catalog(self._manager))]

    @staticmethod
    def is_module_tool(name: str) -> bool:
        return name.startswith(MODULE_TOOL_PREFIX)

    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        args = args or {}
        if name not in TOOL_NAMES:
            if self.is_module_tool(name):
                tool = self._find_module_tool(name)
                if tool is not None:
                    return self._execute_module_tool(tool, args)
            return {
                "ok": False,
                "result": {"error": {"code": "UNKNOWN_TOOL", "message": f"unknown tool: {name}"}},
                "summary": f"未知工具 {name[:40]}",
                "citations": [],
            }
        try:
            handler = getattr(self, f"_tool_{name}")
            result, summary = handler(args)
        except ToolError as exc:
            return {
                "ok": False,
                "result": {"error": {"code": exc.code, "message": exc.message}},
                "summary": f"{name} 失败：{exc.code}",
                "citations": [],
            }
        except Exception:
            logger.exception("tool failed name=%s", name)
            return {
                "ok": False,
                "result": {"error": {"code": "TOOL_FAILED", "message": "tool execution failed"}},
                "summary": f"{name} 失败：TOOL_FAILED",
                "citations": [],
            }
        return {"ok": True, "result": result, "summary": summary, "citations": self._citations(name, result)}

    # ------------------------------------------------------------------ 模块工具
    def _find_module_tool(self, name: str) -> ModuleTool | None:
        """每次执行都重读注册表：撤销授权或禁用模块后立即失效。"""
        for tool in module_tool_catalog(self._manager):
            if tool.alias == name:
                return tool
        return None

    def _execute_module_tool(
        self, tool: ModuleTool, args: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            raw = self._call_module(tool, args)
        except Exception as exc:  # noqa: BLE001 - 模块未运行/超时/报错一律统一映射
            # 只留错误码，不把模块内部 message 交给模型或前端。
            code = str(getattr(exc, "code", "") or type(exc).__name__)[:32]
            logger.warning(
                "module tool failed module=%s tool=%s code=%s",
                tool.module_id,
                tool.tool_id,
                code,
            )
            return {
                "ok": False,
                "result": {
                    "error": {"code": "TOOL_FAILED", "message": "module tool execution failed"}
                },
                "summary": f"{tool.display_name} 失败：TOOL_FAILED",
                "citations": [],
            }
        return {
            "ok": True,
            "result": trim_module_result(raw),
            "summary": f"{tool.display_name} 已完成",
            "citations": [],
        }

    def _call_module(self, tool: ModuleTool, args: dict[str, Any]) -> Any:
        manager = self._manager
        if manager is None:
            from ..modules.api import get_manager

            manager = get_manager()
        return manager.call(tool.module_id, tool.tool_id, args)

    # ------------------------------------------------------------------ 记录
    def _require_record(self, record_id: str) -> RecordTable:
        row = get_record_row(self._session, record_id)
        if row is None or row.deleted_at is not None or row.member_id != self._member_id:
            # 越权与不存在返回同一结果，避免探测其他成员的数据
            raise ToolError("NOT_FOUND", "record not found")
        return row

    def _tool_list_records(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        limit = _as_int(args.get("limit"), 5, minimum=1, maximum=20)
        statement = (
            select(RecordTable)
            .where(
                RecordTable.member_id == self._member_id,
                RecordTable.deleted_at.is_(None),
            )
            .order_by(RecordTable.captured_at.desc(), RecordTable.id.desc())
            .limit(limit)
        )
        rows = list(self._session.exec(statement))
        items = []
        for row in rows:
            latest = analysis_repo.latest_row(self._session, row.id)
            items.append(self._record_brief(row, latest))
        return (
            {"items": items, "count": len(items)},
            f"{len(items)} 条记录",
        )

    def _tool_get_record(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        record_id = _as_str(args.get("recordId"), "recordId")
        row = self._require_record(record_id)
        latest = analysis_repo.latest_row(self._session, record_id)
        return self._record_brief(row, latest), f"记录 {record_id}"

    def _record_brief(self, row: RecordTable, latest: Any) -> dict[str, Any]:
        data = row.data or {}
        quality = data.get("quality") or {}
        return {
            "id": row.id,
            "recordType": row.record_type,
            "capturedAt": data.get("capturedAt"),
            "durationSec": data.get("durationSec"),
            "leads": data.get("leads") or [],
            "samplingRate": data.get("samplingRate"),
            # 标签由用户手输，可能是敏感描述；只给数量，不给原文。
            "tagCount": len(data.get("tags") or []),
            "qualityLevel": quality.get("level") if isinstance(quality, dict) else None,
            "latestAnalysis": _analysis_brief(latest),
        }

    # ------------------------------------------------------------------ 分析
    def _require_analysis(self, analysis_id: str) -> Any:
        row = analysis_repo.get_analysis_row(self._session, analysis_id)
        if row is None:
            raise ToolError("NOT_FOUND", "analysis not found")
        record = get_record_row(self._session, row.record_id)
        if record is None or record.deleted_at is not None or record.member_id != self._member_id:
            raise ToolError("NOT_FOUND", "analysis not found")
        return row

    def _tool_get_analysis(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        analysis_id = _as_str(args.get("analysisId"), "analysisId")
        row = self._require_analysis(analysis_id)
        data = row.data or {}
        quality = data.get("quality") or {}
        warnings = [
            {"code": item.get("code"), "severity": item.get("severity"), "message": item.get("message")}
            for item in (data.get("warnings") or [])
            if isinstance(item, dict)
        ][:10]
        result = {
            "id": row.id,
            "recordId": row.record_id,
            "status": row.status,
            "summary": data.get("summary"),
            "quality": {
                "score": quality.get("score") if isinstance(quality, dict) else None,
                "level": quality.get("level") if isinstance(quality, dict) else None,
            },
            "warnings": warnings,
            "durationMs": data.get("durationMs"),
            "modelId": data.get("modelId"),
            "modelVersion": data.get("modelVersion"),
            "beatsTotal": len(data.get("beats") or []),
            "measurementsIncluded": False,
            "error": data.get("error"),
        }
        return result, f"分析 {row.status}"

    def _tool_get_measurements(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        analysis_id = _as_str(args.get("analysisId"), "analysisId")
        row = self._require_analysis(analysis_id)
        items = analysis_repo.measurements_for(self._session, row.id)
        trimmed = [
            {
                "code": item.get("code"),
                "label": item.get("label"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "ucum": item.get("ucum"),
                "confidence": item.get("confidence"),
                "warnings": item.get("warnings") or [],
            }
            for item in items
            if isinstance(item, dict)
        ]
        return (
            {"analysisId": row.id, "items": trimmed, "count": len(trimmed)},
            f"{len(trimmed)} 个测量值",
        )

    # ------------------------------------------------------------------ 趋势
    def _tool_get_trends(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        metrics = args.get("metrics")
        if isinstance(metrics, str):
            metrics = [part.strip() for part in metrics.split(",") if part.strip()]
        if not isinstance(metrics, list):
            metrics = []
        codes = [str(item) for item in metrics if isinstance(item, (str, int))][:6]
        days = _as_int(args.get("days"), 30, minimum=1, maximum=365)

        try:
            from ..trends import build_trends, parse_metrics
            from ..trends.metrics import METRIC_CATALOG
        except Exception:  # noqa: BLE001 - B3-02 未就绪时工具降级为 unavailable
            return (
                {"available": False, "reason": "trends_unavailable", "series": []},
                "趋势功能未启用",
            )

        unknown = [code for code in codes if code not in METRIC_CATALOG]
        if unknown:
            raise ToolError("INVALID_ARGUMENT", f"unknown metric: {', '.join(unknown)}")
        resolved = codes or parse_metrics(None)
        since = to_storage_dt(utc_now() - timedelta(days=days))
        series = build_trends(
            self._session,
            metrics=resolved,
            since=since,
            until=None,
            member_id=self._member_id,
        )
        compact = []
        for item in series:
            points = item.get("points") or []
            compact.append(
                {
                    "metric": item.get("metric"),
                    "label": item.get("label"),
                    "unit": item.get("unit"),
                    "summary": item.get("summary"),
                    # 只保留最近 20 个点，避免把整段历史塞进上下文
                    "points": points[-20:],
                    "truncated": max(0, len(points) - 20),
                }
            )
        return (
            {"available": True, "days": days, "series": compact},
            f"{len(compact)} 条趋势",
        )

    # ------------------------------------------------------------------ 模型卡
    def _tool_get_model_card(self, _args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        try:
            from ..analysis_service import get_analysis_service
        except Exception:  # noqa: BLE001 - 引擎服务缺失时返回不可用
            return (
                {"available": False, "reason": "engine_unavailable"},
                "模型卡不可用",
            )
        status = get_analysis_service().engine_status()
        card = status.get("modelCard") or {}
        return (
            {
                "available": bool(card),
                "status": status.get("status"),
                "engine": status.get("engine"),
                "modelId": status.get("modelId"),
                "modelVersion": status.get("modelVersion"),
                "card": card,
            },
            "模型卡",
        )

    # ------------------------------------------------------------------ 分析控制
    def _analysis_service(self) -> Any:
        from ..analysis_service import get_analysis_service

        return get_analysis_service()

    def _owned_active_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """队列是全局的；对模型只暴露当前成员记录上的任务。"""
        owned: list[dict[str, Any]] = []
        for item in items:
            record_id = item.get("recordId")
            if not isinstance(record_id, str):
                continue
            row = get_record_row(self._session, record_id)
            if row is None or row.deleted_at is not None or row.member_id != self._member_id:
                continue
            owned.append(item)
        return owned

    def _tool_get_analysis_queue(self, _args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        status = self._analysis_service().queue_status()
        active = self._owned_active_items(list(status.get("active") or []))
        running_id = status.get("runningAnalysisId")
        owned_running = next(
            (item for item in active if item.get("analysisId") == running_id), None
        )
        engine = status.get("engine") or {}
        result = {
            "paused": bool(status.get("paused")),
            "running": owned_running,
            "active": active,
            "activeCount": len(active),
            "queuedInMemory": status.get("queuedInMemory"),
            "jobTimeoutSeconds": status.get("jobTimeoutSeconds"),
            "engine": {
                "status": engine.get("status"),
                "engine": engine.get("engine"),
                "modelId": engine.get("modelId"),
                "modelVersion": engine.get("modelVersion"),
                "message": engine.get("message"),
                "error": engine.get("error"),
                "warmupSeconds": engine.get("warmupSeconds"),
            },
        }
        summary = (
            f"队列{'已暂停' if result['paused'] else '运行中'}，"
            f"我的活跃分析 {len(active)} 条"
        )
        return result, summary

    def _tool_list_analyses(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        record_id = _as_str(args.get("recordId"), "recordId")
        self._require_record(record_id)
        limit = _as_int(args.get("limit"), 10, minimum=1, maximum=50)
        rows = analysis_repo.list_analysis_rows(
            self._session, record_id, limit=limit, offset=0
        )
        items = [analysis_repo.summary_of(row) for row in rows]
        return (
            {"recordId": record_id, "items": items, "count": len(items)},
            f"{len(items)} 条分析",
        )

    def _tool_start_analysis(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        record_id = _as_str(args.get("recordId"), "recordId")
        self._require_record(record_id)
        if not list_signal_rows(self._session, record_id):
            raise ToolError("NO_SIGNAL", "record has no signal to analyze")
        engine = str(args.get("engine") or "cardia")
        options: dict[str, Any] = {}
        if args.get("allowShortRecord") is not None:
            options["allowShortRecord"] = bool(args["allowShortRecord"])
        if args.get("tailMode") in {"pad", "drop"}:
            options["tailMode"] = args["tailMode"]
        try:
            accepted, reused = self._analysis_service().submit(
                record_id=record_id,
                engine=engine,
                options=options,
                force=bool(args.get("force", False)),
            )
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "ANALYSIS_START_FAILED")[:48]
            message = str(getattr(exc, "message", "") or "无法开始分析")[:200]
            raise ToolError(code, message) from exc
        return (
            {**accepted, "reused": reused},
            f"已{'复用' if reused else '提交'}分析 {accepted.get('analysisId')}",
        )

    def _tool_cancel_analysis(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        analysis_id = _as_str(args.get("analysisId"), "analysisId")
        self._require_analysis(analysis_id)
        try:
            result = self._analysis_service().cancel(analysis_id)
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "ANALYSIS_CANCEL_FAILED")[:48]
            raise ToolError(code, "无法取消分析") from exc
        return result, f"分析 {analysis_id}：{result.get('status')}"

    def _tool_retry_analysis(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        analysis_id = _as_str(args.get("analysisId"), "analysisId")
        self._require_analysis(analysis_id)
        try:
            accepted, reused = self._analysis_service().retry(analysis_id)
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "ANALYSIS_RETRY_FAILED")[:48]
            raise ToolError(code, "无法重试分析") from exc
        return (
            {**accepted, "retriedFrom": analysis_id, "reused": reused},
            f"已重新提交分析 {accepted.get('analysisId')}",
        )

    def _tool_pause_analysis_queue(self, _args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        status = self._analysis_service().pause_queue()
        return (
            {"paused": bool(status.get("paused")), "activeCount": len(self._owned_active_items(status.get("active") or []))},
            "分析队列已暂停",
        )

    def _tool_resume_analysis_queue(self, _args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        status = self._analysis_service().resume_queue()
        return (
            {"paused": bool(status.get("paused")), "activeCount": len(self._owned_active_items(status.get("active") or []))},
            "分析队列已恢复",
        )

    def _tool_recover_stuck_analyses(
        self, args: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        max_age = args.get("maxAgeSeconds")
        try:
            limit = float(max_age) if max_age is not None else None
        except (TypeError, ValueError):
            raise ToolError("INVALID_ARGUMENT", "maxAgeSeconds must be a number") from None
        if limit is not None and limit < 0:
            raise ToolError("INVALID_ARGUMENT", "maxAgeSeconds must be >= 0")
        service = self._analysis_service()
        recovered = service.repair_stalled(max_age_s=limit)
        status = service.queue_status()
        return (
            {
                "recovered": recovered,
                "paused": bool(status.get("paused")),
                "activeCount": len(self._owned_active_items(status.get("active") or [])),
            },
            f"已修复 {recovered} 条卡死分析",
        )

    # ------------------------------------------------------------------ 仪表盘卡片
    def _tool_list_card_templates(
        self, _args: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        from ..dashboard_cards.catalog import templates

        items = [template.model_dump(mode="json") for template in templates()]
        return {"items": items, "count": len(items)}, f"{len(items)} 个卡片模板"

    def _tool_create_dashboard_card(
        self, args: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        from pydantic import ValidationError as PydanticValidationError

        from ..dashboard_cards import service
        from ..dashboard_cards.catalog import spec_for
        from ..dashboard_cards.models import CardFields
        from ..domain.errors import ApiError

        kind = args.get("kind")
        spec = spec_for(kind) if isinstance(kind, str) else None
        aggregation = str(args.get("aggregation") or "latest")
        title = str(args.get("title") or "").strip()
        if not title:
            label = spec.label_zh if spec is not None else "自定义"
            title = f"{label} · {aggregation}"

        raw: dict[str, Any] = {"title": title, "kind": kind}
        for key in ("aggregation", "windowDays", "view", "unit", "colorToken"):
            value = args.get(key)
            if value is not None:
                raw[key] = value
        try:
            fields = CardFields.model_validate(raw)
        except PydanticValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            detail = ".".join(str(part) for part in first.get("loc", ())) or "card"
            raise ToolError(
                "INVALID_ARGUMENT",
                f"card field {detail}: {first.get('msg', 'invalid')}",
            ) from exc

        try:
            draft = service.create_draft(
                self._session,
                member_id=self._member_id,
                fields=fields,
                created_by="agent",
            )
        except ApiError as exc:
            raise ToolError(exc.code, exc.message) from exc

        return (
            {
                "saved": False,
                "draftId": draft.id,
                "card": draft.card.model_dump(mode="json"),
                "preview": draft.preview.model_dump(mode="json") if draft.preview else None,
                "needsConfirmation": True,
            },
            f"已生成卡片草稿：{draft.card.title}",
        )

    def _tool_confirm_dashboard_card(
        self, args: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        from ..dashboard_cards import service
        from ..domain.errors import ApiError

        draft_id = _as_str(args.get("draftId"), "draftId")
        try:
            card = service.confirm_draft(
                self._session, member_id=self._member_id, draft_id=draft_id
            )
            data = service.card_data(self._session, card)
        except ApiError as exc:
            raise ToolError(exc.code, exc.message) from exc
        return (
            {
                "saved": True,
                "card": card.model_dump(mode="json"),
                "data": data.model_dump(mode="json"),
            },
            f"已保存卡片：{card.title}",
        )

    # ------------------------------------------------------------------ 引用
    def _citations(self, name: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """为前端生成可点击 chip；不包含敏感内容。"""
        citations: list[dict[str, Any]] = []
        if name == "list_records":
            for item in result.get("items") or []:
                citations.append(
                    {
                        "kind": "record",
                        "id": item.get("id"),
                        "label": item.get("capturedAt") or item.get("id"),
                        "recordId": item.get("id"),
                    }
                )
        elif name == "get_record":
            citations.append(
                {
                    "kind": "record",
                    "id": result.get("id"),
                    "label": result.get("capturedAt") or result.get("id"),
                    "recordId": result.get("id"),
                }
            )
            latest = result.get("latestAnalysis") or {}
            if latest.get("id"):
                citations.append(
                    {
                        "kind": "analysis",
                        "id": latest.get("id"),
                        "label": latest.get("summary") or latest.get("status") or latest.get("id"),
                        "recordId": result.get("id"),
                    }
                )
        elif name in {"get_analysis", "get_measurements"}:
            analysis_id = result.get("id") or result.get("analysisId")
            citations.append(
                {
                    "kind": "analysis",
                    "id": analysis_id,
                    "label": result.get("summary") or "分析结果",
                    "recordId": result.get("recordId"),
                }
            )
        elif name == "get_trends":
            for series in result.get("series") or []:
                points = series.get("points") or []
                if points:
                    citations.append(
                        {
                            "kind": "trend",
                            "id": series.get("metric"),
                            "label": f"{series.get('label')} · {len(points)} 点",
                            "recordId": points[-1].get("recordId"),
                        }
                    )
        elif name == "get_model_card" and result.get("available"):
            citations.append(
                {
                    "kind": "model",
                    "id": result.get("modelId"),
                    "label": f"{result.get('modelId')} {result.get('modelVersion') or ''}".strip(),
                }
            )
        elif name == "create_dashboard_card":
            draft_id = result.get("draftId")
            card = result.get("card") or {}
            if draft_id:
                citations.append(
                    {
                        "kind": "card-draft",
                        "id": draft_id,
                        "label": f"草稿 · {card.get('title') or card.get('kind') or ''}".strip(),
                    }
                )
        elif name == "confirm_dashboard_card":
            card = result.get("card") or {}
            if card.get("id"):
                citations.append(
                    {
                        "kind": "dashboard-card",
                        "id": card.get("id"),
                        "label": card.get("title") or card.get("kind") or card.get("id"),
                    }
                )
        elif name in {"start_analysis", "retry_analysis"}:
            analysis_id = result.get("analysisId")
            if analysis_id:
                citations.append(
                    {
                        "kind": "analysis",
                        "id": analysis_id,
                        "label": f"分析 {result.get('status') or 'queued'}",
                        "recordId": result.get("recordId"),
                    }
                )
        elif name == "cancel_analysis":
            analysis_id = result.get("analysisId")
            if analysis_id:
                citations.append(
                    {
                        "kind": "analysis",
                        "id": analysis_id,
                        "label": f"分析 {result.get('status') or 'cancelled'}",
                    }
                )
        elif name == "get_analysis_queue":
            running = result.get("running") or {}
            if running.get("analysisId"):
                progress = running.get("progress") or {}
                citations.append(
                    {
                        "kind": "analysis",
                        "id": running.get("analysisId"),
                        "label": f"运行中 {progress.get('percent', 0)}%",
                        "recordId": running.get("recordId"),
                    }
                )
        # 去重（同一引用在多次工具调用中重复出现）
        seen: set[tuple[str, Any]] = set()
        unique: list[dict[str, Any]] = []
        for citation in citations:
            marker = (str(citation.get("kind")), citation.get("id"))
            if marker in seen or not citation.get("id"):
                continue
            seen.add(marker)
            unique.append({key: value for key, value in citation.items() if value is not None})
        return unique[:20]


def new_tool_call_id() -> str:
    """生成一次工具调用的可读 ID（也用于 SSE 关联）。"""
    return f"ltc_{uuid7()}"


__all__ = [
    "MODULE_TOOL_PREFIX",
    "TOOL_NAMES",
    "TOOL_SPECS",
    "ModuleTool",
    "ToolBox",
    "ToolError",
    "module_tool_alias",
    "module_tool_catalog",
    "new_tool_call_id",
    "trim_module_result",
]

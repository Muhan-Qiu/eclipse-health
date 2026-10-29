"""只读工具：把「最小可发送切片」暴露给模型。

硬约束：

- 只返回摘要 / 测量 / 质量 / 警告；**不返回波形、notes、成员姓名**；
- 记录与分析必须属于当前成员，否则按 ``NOT_FOUND`` 处理（不泄漏存在性）；
- 工具只读，任何写操作都不在这里。

``execute`` 返回统一结构，供 agent 同时生成 SSE 事件与透明面板摘要：

    {"ok": bool, "result": {...}, "summary": "...", "citations": [...]}
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from ..db import analysis_repo
from ..db.models import RecordTable
from ..db.repositories import get_record_row
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
]

TOOL_NAMES = tuple(spec["function"]["name"] for spec in TOOL_SPECS)


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

    def __init__(self, session: Session, member_id: str) -> None:
        self._session = session
        self._member_id = member_id

    # ------------------------------------------------------------------ 入口
    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        args = args or {}
        if name not in TOOL_NAMES:
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


__all__ = ["TOOL_NAMES", "TOOL_SPECS", "ToolBox", "ToolError", "new_tool_call_id"]

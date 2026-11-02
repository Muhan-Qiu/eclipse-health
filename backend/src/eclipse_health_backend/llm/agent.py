"""对话与工具循环（F1/F2/F4）。

设计要点：

- provider 适配器只负责把「一次模型响应」变成 ``token`` / ``tool_calls`` 事件；
- 工具循环、超时、取消、引用与透明面板都在这里统一处理；
- 事件是纯 dict，API 层只做 SSE 序列化与落库，方便单测直接消费。

不做：多模态、联网搜索、写操作、跨成员上下文。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Self

import httpx
from sqlmodel import Session, select

from ..db import analysis_repo
from ..db.models import RecordTable
from ..db.repositories import get_record_row
from ..domain.ids import uuid7
from .providers import Provider
from .tools import TOOL_SPECS, ToolBox

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 5
MAX_TOOL_ROUNDS = 5
# 首 token 可能包含本地模型冷加载（9B 量级约 10–20 s），给足余量。
TURN_TIMEOUT_S = 90.0
REQUEST_TIMEOUT_S = 45.0
MAX_HISTORY_MESSAGES = 20
# 流式请求在「尚未输出任何内容」时允许重试一次；已输出后重试会重复 token。
MAX_STREAM_RETRIES = 1
RETRY_BACKOFF_S = 0.6

STYLE_INSTRUCTIONS = {
    "brief": "用 2–3 句话回答，先给结论，再给关键数值。",
    "detailed": "分点解释，给出数值与依据，总长度不超过 250 字。",
    "doctor": "使用临床术语，按「发现 / 数据依据 / 建议复核项」组织；仍然不做诊断。",
}

SYSTEM_PROMPT = """你是 eclipse health 的本地分析助手，帮助用户理解自己的心电图分析结果。

规则：
1. 不做诊断、不给处方或治疗建议；用户描述症状时，建议其就医。
2. 只使用工具返回的数据与下方上下文；没有数据就明确说没有，绝不编造数值。
3. 引用数据时给出记录 ID 或分析 ID。
4. 用简体中文回答；用户使用其他语言时跟随用户语言。
5. 工具可以读取摘要与测量值，读不到波形、备注和成员信息，不要假装能看到；create_dashboard_card 只生成待确认的卡片草稿，不会直接保存，只有用户明确同意后才能调用 confirm_dashboard_card。
6. 分析控制工具（start_analysis / cancel_analysis / retry_analysis / pause_analysis_queue / resume_analysis_queue / recover_stuck_analyses）会改变本机任务状态：只有用户明确要求时才调用；调用后如实说明结果，不要连续自动重试。用户反馈「分析卡住/一直 40%/不能分析」时，先用 get_analysis_queue 诊断，再按需取消、修复或重试。
7. 以 m_ 开头的工具由已安装的第三方模块提供，结果仅供参考；与内置工具冲突时以内置结果为准。
8. 回答末尾用一句话提醒：以上为数据解读，不构成医学诊断。"""

COACH_SYSTEM_PROMPT = """你是 eclipse health 的本地健康教练，用数据与用户偏好帮助其建立可持续的生活方式。

规则：
1. 不做诊断、不开处方、不替代医生；不把评分或数据解释成疾病结论。
2. 只使用下方「教练上下文」与工具结果中的评分、健康数据、运动记录、记忆和天气；缺失的数据就明说没有，绝不编造。
3. 建议必须渐进、可执行：一次给 1–3 个小步骤，说明频率与如何判断是否适合自己。
4. 出现红旗症状——胸痛或胸闷伴出汗、晕厥或接近晕厥、明显呼吸困难、心悸伴头晕、运动中胸痛——立即建议停止活动并尽快就医/急诊。
5. 个人记忆只作为背景和偏好，不主动复述敏感细节；用户要求忘记时，提示到健康档案页关闭记忆。
6. 天气只用于调整户外活动建议，不据此做医学判断。
7. 用简体中文回答；用户使用其他语言时跟随用户语言。
8. 回答末尾用一句话提醒：以上为健康建议，不构成医学诊断。"""

SENT_FIELDS_BASE = [
    "system.instructions",
    "tools.definitions",
    "conversation.messages",
]

REDACTIONS_BASE = [
    "record.notes",
    "member.displayName",
    "signal.samples",
    "analysis.beats",
]


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #


class TurnCancelled(Exception):
    """客户端断开或用户点击「停止生成」。"""


class TurnTimeout(Exception):
    """整轮对话超过 ``TURN_TIMEOUT_S``。"""


class LLMError(RuntimeError):
    """已经脱敏的 provider 错误；``message`` 中不含 key 与请求体。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# 上下文与透明面板
# --------------------------------------------------------------------------- #


def _row_summary(row: RecordTable) -> dict[str, Any]:
    data = row.data or {}
    quality = data.get("quality") or {}
    return {
        "id": row.id,
        "recordType": row.record_type,
        "capturedAt": data.get("capturedAt"),
        "durationSec": data.get("durationSec"),
        "leads": data.get("leads") or [],
        "samplingRate": data.get("samplingRate"),
        "tagCount": len(data.get("tags") or []),
        "qualityLevel": quality.get("level") if isinstance(quality, dict) else None,
    }


def _analysis_context(session: Session, record_id: str) -> dict[str, Any] | None:
    row = analysis_repo.latest_row(session, record_id)
    if row is None:
        return None
    data = row.data or {}
    quality = data.get("quality") or {}
    measurements = analysis_repo.measurements_for(session, row.id)
    return {
        "id": row.id,
        "status": row.status,
        "summary": data.get("summary"),
        "quality": {
            "score": quality.get("score") if isinstance(quality, dict) else None,
            "level": quality.get("level") if isinstance(quality, dict) else None,
        },
        "warnings": [
            {
                "code": item.get("code"),
                "severity": item.get("severity"),
                "message": item.get("message"),
            }
            for item in (data.get("warnings") or [])
            if isinstance(item, dict)
        ][:10],
        "measurements": [
            {
                "code": item.get("code"),
                "label": item.get("label"),
                "value": item.get("value"),
                "unit": item.get("unit"),
            }
            for item in measurements
            if isinstance(item, dict)
        ],
    }


def build_context(
    session: Session,
    *,
    member_id: str,
    record_id: str | None,
    include_notes: bool,
) -> dict[str, Any]:
    """构造发送给模型的最小切片；同时返回透明面板需要的元数据。"""
    sent_fields = list(SENT_FIELDS_BASE)
    redactions = [item for item in REDACTIONS_BASE]
    record_ids: list[str] = []
    analysis_ids: list[str] = []
    context: dict[str, Any] = {}

    if record_id:
        row = get_record_row(session, record_id)
        if row is None or row.deleted_at is not None or row.member_id != member_id:
            raise LLMError("record_not_found", "record not found")
        brief = _row_summary(row)
        sent_fields.extend(
            [
                "record.id",
                "record.recordType",
                "record.capturedAt",
                "record.durationSec",
                "record.leads",
                "record.samplingRate",
                "record.quality.level",
            ]
        )
        record_ids.append(row.id)
        if include_notes:
            notes = (row.data or {}).get("notes") or ""
            brief["notes"] = notes
            sent_fields.append("record.notes")
            redactions = [item for item in redactions if item != "record.notes"]

        analysis = _analysis_context(session, row.id)
        if analysis:
            sent_fields.extend(
                [
                    "analysis.id",
                    "analysis.status",
                    "analysis.summary",
                    "analysis.quality",
                    "analysis.warnings",
                    "measurement.code",
                    "measurement.value",
                    "measurement.unit",
                ]
            )
            analysis_ids.append(analysis["id"])
        context = {"record": brief, "latestAnalysis": analysis}
    else:
        statement = (
            select(RecordTable)
            .where(
                RecordTable.member_id == member_id,
                RecordTable.deleted_at.is_(None),
            )
            .order_by(RecordTable.captured_at.desc())
            .limit(3)
        )
        recent = [_row_summary(row) for row in session.exec(statement)]
        sent_fields.extend(
            [
                "record.id",
                "record.capturedAt",
                "record.durationSec",
                "record.leads",
                "record.quality.level",
            ]
        )
        record_ids.extend(item["id"] for item in recent)
        context = {"recentRecords": recent}

    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    return {
        "context": context,
        "contextText": context_text,
        "sentFields": sent_fields,
        "redactions": redactions,
        "recordIds": record_ids,
        "analysisIds": analysis_ids,
        "includeNotes": include_notes,
    }


def approx_tokens(*parts: str) -> int:
    """粗略估算：UTF-8 字节数 / 3，中英文混排比字符数更接近 token。"""
    total = sum(len(part.encode("utf-8")) for part in parts)
    return max(1, total // 3)


def make_usage(
    prompt: Any, completion: Any, *, source: str = "provider"
) -> dict[str, Any]:
    """统一的用量结构；provider 没给就留 ``None``，绝不编造数字。"""
    prompt_tokens = max(0, int(prompt)) if isinstance(prompt, (int, float)) else None
    completion_tokens = (
        max(0, int(completion)) if isinstance(completion, (int, float)) else None
    )
    total = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )
    return {
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "totalTokens": total,
        "source": source,
    }


def merge_usage(total: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any] | None:
    """按轮累加：工具循环每轮都会重新发送增长后的上下文，累计值才对应真实消耗。"""
    if not extra:
        return total
    if total is None:
        return dict(extra)
    merged = dict(total)
    for key in ("promptTokens", "completionTokens", "totalTokens"):
        left, right = total.get(key), extra.get(key)
        if left is None or right is None:
            if key == "totalTokens":
                continue
            # 某一轮缺数据时保留已知值，不把缺失当 0
            merged[key] = left if right is None else right
        else:
            merged[key] = int(left) + int(right)
    merged["source"] = (
        "provider"
        if "provider" in {_usage_source(total), _usage_source(extra)}
        else "estimate"
    )
    return merged


def _usage_source(usage: dict[str, Any] | None) -> str | None:
    """没有数字的 usage（例如 provider 只回了一个空对象）不参与来源判断。"""
    if usage is None:
        return None
    if not any(
        usage.get(key) is not None
        for key in ("promptTokens", "completionTokens", "totalTokens")
    ):
        return None
    return "provider" if usage.get("source") == "provider" else "estimate"


def build_transparency(
    provider: Provider,
    *,
    context: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_calls: int = 0,
) -> dict[str, Any]:
    payload = json.dumps(
        {"messages": messages, "tools": TOOL_SPECS}, ensure_ascii=False, default=str
    )
    return {
        "provider": {
            "id": provider.id,
            "kind": provider.kind,
            "label": provider.label,
            "model": provider.model,
        },
        "model": provider.model,
        "sentFields": context["sentFields"],
        "redactions": context["redactions"],
        "approxTokens": approx_tokens(context["contextText"], payload),
        "recordIds": context["recordIds"],
        "analysisIds": context["analysisIds"],
        "includeNotes": context["includeNotes"],
        "toolCalls": tool_calls,
        "usage": None,
        "localOnly": provider.is_local,
    }


def build_messages(
    *,
    context_text: str,
    history: list[dict[str, Any]],
    content: str,
    style: str,
    mode: str | None = None,
    coach_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    style_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["brief"])
    if mode == "coach":
        # 惰性导入：普通对话不多加载教练模块，G2/G3 缺失也不影响启动。
        from ..coach.context import render_coach_context

        system = (
            f"{COACH_SYSTEM_PROMPT}\n\n回答风格：{style_instruction}\n\n"
            "教练上下文（只读，缺失段落已省略）：\n"
            f"{render_coach_context(coach_context)}\n\n"
            f"本地记录上下文（只读，可能为空）：\n{context_text}"
        )
    else:
        system = (
            f"{SYSTEM_PROMPT}\n\n回答风格：{style_instruction}\n\n"
            f"本地上下文（只读，可能为空）：\n{context_text}"
        )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": content})
    return messages


# --------------------------------------------------------------------------- #
# Provider 适配器
# --------------------------------------------------------------------------- #


_HTTP_STATUS_MAP: dict[int, tuple[str, str]] = {
    400: ("bad_request", "{kind} rejected the request (HTTP 400)"),
    401: ("auth_error", "{kind} authentication failed (HTTP 401) — check the API key"),
    403: ("auth_error", "{kind} access denied (HTTP 403) — check API key permissions"),
    404: ("not_found", "{kind} endpoint or model not found (HTTP 404)"),
    408: ("timeout", "{kind} request timed out (HTTP 408)"),
    413: ("bad_request", "{kind} request too large (HTTP 413)"),
    422: ("bad_request", "{kind} rejected the request (HTTP 422)"),
    429: ("rate_limited", "{kind} is rate limited (HTTP 429) — retry later"),
}

TRANSIENT_CODE_SUFFIXES = ("_rate_limited", "_server_error", "_network_error")


def _is_connection_error(exc: BaseException) -> bool:
    """沿异常链识别连接失败；LiteLLM 常把 ``ConnectError`` 包成 500。"""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, httpx.ConnectError):
            return True
        name = type(current).__name__.lower()
        if ("connect" in name or "connection" in name) and (
            "error" in name or "exception" in name
        ):
            return True
        for attr in ("__cause__", "__context__", "original_exception"):
            nested = getattr(current, attr, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
        for arg in getattr(current, "args", ()):
            if isinstance(arg, BaseException):
                pending.append(arg)
    return False


def _sanitize(kind: str, exc: BaseException, *, status: int | None = None) -> LLMError:
    """只保留 provider 类型与 HTTP 状态；绝不透传原始异常文本。"""
    if _is_connection_error(exc):
        return LLMError(f"{kind}_network_error", f"{kind} connection failed")
    if status is not None:
        if 500 <= status <= 599:
            return LLMError(
                f"{kind}_server_error", f"{kind} server error (HTTP {status})"
            )
        code, template = _HTTP_STATUS_MAP.get(
            status, ("http_error", "{kind} request failed (HTTP {status})")
        )
        return LLMError(f"{kind}_{code}", template.format(kind=kind, status=status))
    if isinstance(exc, httpx.TimeoutException):
        return LLMError("timeout", f"{kind} request timed out")
    if isinstance(exc, httpx.HTTPError):
        return LLMError(f"{kind}_network_error", f"{kind} connection failed")
    return LLMError(f"{kind}_error", f"{kind} request failed ({type(exc).__name__})")


def is_retryable(error: LLMError | None) -> bool:
    """只有「重发不会产生重复内容」的错误才允许重试。"""
    if error is None:
        return False
    return error.code.endswith(TRANSIENT_CODE_SUFFIXES)


class ChatAdapter:
    """把 provider 的一次响应转换成统一 chunk。"""

    def __init__(self, provider: Provider, api_key: str | None) -> None:
        self.provider = provider
        self.api_key = api_key

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        cancel: asyncio.Event,
    ) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError


class MockAdapter(ChatAdapter):
    """确定性回复：没有 key 也能演示完整的工具循环。"""

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        cancel: asyncio.Event,
    ) -> AsyncIterator[dict[str, Any]]:
        called = {
            str(message.get("name") or "")
            for message in messages
            if message.get("role") == "tool"
        }
        latest_analysis = _latest_analysis_from_tools(messages)

        if "list_records" not in called:
            yield {"type": "tool_calls", "calls": [_call("list_records", {"limit": 5})]}
            return
        if latest_analysis.get("id") and "get_analysis" not in called:
            yield {
                "type": "tool_calls",
                "calls": [_call("get_analysis", {"analysisId": latest_analysis["id"]})],
            }
            return
        if latest_analysis.get("id") and "get_measurements" not in called:
            yield {
                "type": "tool_calls",
                "calls": [_call("get_measurements", {"analysisId": latest_analysis["id"]})],
            }
            return

        text = _mock_answer(messages, latest_analysis)
        for index in range(0, len(text), 12):
            if cancel.is_set():
                return
            yield {"type": "token", "text": text[index : index + 12]}
            await asyncio.sleep(0)
        # Mock 没有真实计费数据，按字节估算并明确标注 source=estimate。
        yield {
            "type": "usage",
            "usage": make_usage(
                approx_tokens(json.dumps(messages, ensure_ascii=False, default=str)),
                approx_tokens(text),
                source="estimate",
            ),
        }


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"id": f"call_{uuid7().hex}", "name": name, "args": args}


def _latest_analysis_from_tools(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        try:
            payload = json.loads(message.get("content") or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("items"):
            for item in payload["items"]:
                latest = (item or {}).get("latestAnalysis") or {}
                if latest.get("id"):
                    return latest
    return {}


def _measurements_from_tools(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool" and message.get("name") == "get_measurements":
            try:
                payload = json.loads(message.get("content") or "{}")
            except (TypeError, ValueError):
                return {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _mock_answer(messages: list[dict[str, Any]], latest: dict[str, Any]) -> str:
    measurements = _measurements_from_tools(messages)
    items = measurements.get("items") or []
    by_code = {
        str(item.get("code")): item
        for item in items
        if isinstance(item, dict) and item.get("code")
    }
    if not latest.get("id"):
        return (
            "我查到当前成员最近的记录，但还没有已完成的分析结果。"
            "请先在记录详情页运行一次分析，再来问我。\n\n"
            "以上为数据解读，不构成医学诊断。"
        )
    if latest.get("status") != "completed":
        return (
            f"这条记录的最新分析状态是 {latest.get('status')}，还没有可解读的测量值。\n\n"
            "以上为数据解读，不构成医学诊断。"
        )

    parts: list[str] = []
    heart_rate = by_code.get("heart_rate_mean")
    if heart_rate and heart_rate.get("value") is not None:
        parts.append(f"平均心率 {heart_rate['value']} {heart_rate.get('unit') or 'bpm'}")
    rmssd = by_code.get("rmssd")
    if rmssd and rmssd.get("value") is not None:
        parts.append(f"RMSSD {rmssd['value']} {rmssd.get('unit') or 'ms'}")
    ratios = [by_code.get(code) for code in ("svb_ratio", "veb_ratio", "f_ratio")]
    abnormal = sum(
        float(item["value"])
        for item in ratios
        if item and item.get("value") is not None
    )
    if any(item and item.get("value") is not None for item in ratios):
        parts.append(f"室上性/室性/融合搏动合计 {abnormal:.2f}%")

    if parts:
        body = "根据解析到的分析结果：" + "，".join(parts) + "。"
    else:
        body = f"最新分析（{latest.get('summary') or '已完成的逐搏分类'}）没有可用的测量值。"
    return f"{body}\n\n以上为数据解读，不构成医学诊断。"


class OllamaAdapter(ChatAdapter):
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        cancel: asyncio.Event,
    ) -> AsyncIterator[dict[str, Any]]:
        base = (self.provider.base_url or "http://127.0.0.1:11434").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.provider.model,
            "messages": [_ollama_message(message) for message in messages],
            "stream": True,
        }
        # 不主动关闭 think：qwen3:4b 这类模型关了 think 会把推理塞进 content 且不调用工具。
        # 需要更快首字时可由 provider.options 显式设置。
        think_option = self.provider.options.get("think")
        if think_option is not None:
            payload["think"] = bool(think_option)
        if tools:
            payload["tools"] = tools

        calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None
        try:
            async with (
                httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client,
                client.stream("POST", f"{base}/api/chat", json=payload) as response,
            ):
                if response.status_code >= 400:
                    raise _sanitize("ollama", RuntimeError("http"), status=response.status_code)
                async for line in response.aiter_lines():
                    if cancel.is_set():
                        return
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    message = chunk.get("message") or {}
                    text = message.get("content")
                    if text:
                        yield {"type": "token", "text": text}
                    for raw in message.get("tool_calls") or []:
                        function = raw.get("function") or {}
                        name = function.get("name")
                        if not name:
                            continue
                        args = function.get("arguments")
                        calls.append(
                            {
                                "id": f"call_{uuid7().hex}",
                                "name": str(name),
                                "args": args if isinstance(args, dict) else _parse_arguments(args),
                            }
                        )
                    if chunk.get("done"):
                        usage = make_usage(
                            chunk.get("prompt_eval_count"), chunk.get("eval_count")
                        )
                        break
        except LLMError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 统一脱敏
            raise _sanitize("ollama", exc) from None

        if calls:
            yield {"type": "tool_calls", "calls": calls}
        if usage is not None:
            yield {"type": "usage", "usage": usage}


def _ollama_message(message: dict[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    content = message.get("content") or ""
    if role == "tool":
        return {
            "role": "tool",
            "content": content,
            "tool_name": message.get("name") or "",
        }
    if role == "assistant" and message.get("tool_calls"):
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "function": {
                        "name": call["function"]["name"],
                        "arguments": _parse_arguments(call["function"]["arguments"]),
                    }
                }
                for call in message["tool_calls"]
            ],
        }
    return {"role": role or "user", "content": content}


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class LiteLLMAdapter(ChatAdapter):
    """openai / anthropic 统一走 LiteLLM（惰性导入，避免拖慢启动）。"""

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        cancel: asyncio.Event,
    ) -> AsyncIterator[dict[str, Any]]:
        if self.provider.needs_key and not self.api_key:
            raise LLMError("missing_api_key", "provider API key is not configured")
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - 依赖已在环境中
            raise LLMError("litellm_missing", "LiteLLM is not installed") from exc

        kwargs: dict[str, Any] = {
            "model": self.provider.litellm_model,
            "messages": messages,
            "stream": True,
            "timeout": REQUEST_TIMEOUT_S,
        }
        if tools:
            kwargs["tools"] = tools
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.provider.base_url:
            kwargs["api_base"] = self.provider.base_url
        if self.provider.litellm_provider == "openai":
            # OpenAI 兼容端点默认不在流里带 usage，需要显式要求。
            kwargs["stream_options"] = {"include_usage": True}

        calls: dict[int, dict[str, Any]] = {}
        usage_parts: dict[str, int | None] = {
            "promptTokens": None,
            "completionTokens": None,
            "totalTokens": None,
        }
        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                if cancel.is_set():
                    return
                raw_usage = _iter_usage_payloads(chunk)
                for payload in raw_usage:
                    _merge_usage_parts(usage_parts, payload)
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                text = getattr(delta, "content", None) if delta is not None else None
                if text:
                    yield {"type": "token", "text": text}
                for raw_call in getattr(delta, "tool_calls", None) or []:
                    index = int(getattr(raw_call, "index", 0) or 0)
                    slot = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if getattr(raw_call, "id", None):
                        slot["id"] = str(raw_call.id)
                    function = getattr(raw_call, "function", None)
                    if function is not None:
                        if getattr(function, "name", None):
                            slot["name"] += str(function.name)
                        if getattr(function, "arguments", None):
                            slot["arguments"] += str(function.arguments)
        except LLMError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 统一脱敏
            status = getattr(exc, "status_code", None)
            raise _sanitize(self.provider.error_kind, exc, status=status) from None

        ordered = [calls[index] for index in sorted(calls)]
        if ordered:
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": item["id"] or f"call_{uuid7().hex}",
                        "name": item["name"],
                        "args": _parse_arguments(item["arguments"]),
                    }
                    for item in ordered
                    if item["name"]
                ],
            }
        usage = _usage_from_parts(usage_parts)
        if usage is not None:
            yield {"type": "usage", "usage": usage}


def _raw_usage_value(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    value = getattr(raw, key, None)
    if value is not None:
        return value
    extra = getattr(raw, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(key)
    return None


def _usage_value(raw: Any, key: str) -> int | None:
    value = _raw_usage_value(raw, key)
    return int(value) if isinstance(value, (int, float)) else None


_USAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "promptTokens": ("prompt_tokens", "input_tokens"),
    "completionTokens": ("completion_tokens", "output_tokens"),
}


def _usage_number(raw: Any, keys: tuple[str, ...]) -> int | None:
    """优先 provider 的规范字段；为 0 时回退到 Anthropic 的 *input_tokens。"""
    fallback: int | None = None
    for key in keys:
        value = _usage_value(raw, key)
        if value is None:
            continue
        if value > 0:
            return value
        if fallback is None:
            fallback = value
    return fallback


def _iter_usage_payloads(chunk: Any) -> list[Any]:
    """LiteLLM 不同版本把 usage 放在不同位置；只读已知容器，不做递归。"""
    payloads: list[Any] = []
    if isinstance(chunk, dict):
        payloads.append(chunk.get("usage"))
    else:
        payloads.append(getattr(chunk, "usage", None))
    for attr in ("model_extra", "_hidden_params", "provider_specific_fields"):
        container = getattr(chunk, attr, None)
        if isinstance(container, dict):
            for key in ("usage", "anthropic_usage", "token_usage"):
                payloads.append(container.get(key))
    for choice in getattr(chunk, "choices", None) or []:
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        payloads.append(getattr(delta, "usage", None))
        for attr in ("model_extra", "provider_specific_fields"):
            container = getattr(delta, attr, None)
            if isinstance(container, dict):
                payloads.append(container.get("usage"))
    return [item for item in payloads if item is not None]


def _merge_usage_parts(parts: dict[str, int | None], raw: Any) -> None:
    for target, keys in _USAGE_FIELDS.items():
        value = _usage_number(raw, keys)
        # 空 usage 对象（全 0）不能覆盖已知的真实值。
        if value is not None and (value > 0 or parts[target] is None):
            parts[target] = value
    total = _usage_value(raw, "total_tokens")
    if total is not None and total > 0:
        parts["totalTokens"] = total


def _usage_from_parts(parts: dict[str, int | None]) -> dict[str, Any] | None:
    prompt = parts.get("promptTokens")
    completion = parts.get("completionTokens")
    total = parts.get("totalTokens")
    if prompt is None and completion is None and total is None:
        return None
    if (total is None or total == 0) and prompt is not None and completion is not None:
        total = prompt + completion
    return {
        "promptTokens": prompt,
        "completionTokens": completion,
        "totalTokens": total,
        "source": "provider",
    }


def adapter_for(provider: Provider, api_key: str | None) -> ChatAdapter:
    if provider.kind == "mock":
        return MockAdapter(provider, None)
    if provider.kind == "ollama":
        return OllamaAdapter(provider, None)
    return LiteLLMAdapter(provider, api_key)


# --------------------------------------------------------------------------- #
# 工具循环
# --------------------------------------------------------------------------- #


class _Guard:
    """把「整轮截止时间」和「取消事件」统一到一个 await 上。"""

    def __init__(self, cancel: asyncio.Event, timeout_s: float) -> None:
        self._cancel = cancel
        self._deadline = time.monotonic() + timeout_s
        self._cancel_task: asyncio.Future[bool] | None = None

    async def __aenter__(self) -> Self:
        self._cancel_task = asyncio.ensure_future(self._cancel.wait())
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._cancel_task is not None:
            self._cancel_task.cancel()

    async def next(self, iterator: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TurnTimeout
        if self._cancel.is_set():
            raise TurnCancelled
        assert self._cancel_task is not None
        next_task = asyncio.ensure_future(iterator.__anext__())
        done, _pending = await asyncio.wait(
            {next_task, self._cancel_task},
            timeout=remaining,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if next_task in done:
            return next_task.result()
        next_task.cancel()
        if self._cancel_task in done:
            raise TurnCancelled
        raise TurnTimeout


async def _sleep_or_cancel(cancel: asyncio.Event, seconds: float) -> None:
    """重试退避期间保持可取消。"""
    if seconds <= 0:
        return
    try:
        await asyncio.wait_for(cancel.wait(), timeout=seconds)
    except TimeoutError:
        return
    raise TurnCancelled


async def _close_stream(stream: AsyncIterator[dict[str, Any]]) -> None:
    """丢弃失败的流时显式关闭底层连接，避免 HTTP 客户端连接泄漏。"""
    close = getattr(stream, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        logger.debug("llm stream close failed", exc_info=True)


def _truncate_tool_result(result: dict[str, Any], limit: int = 12_000) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return json.dumps(
        {"truncated": True, "preview": text[:limit], "note": "result truncated"},
        ensure_ascii=False,
    )


def _dedupe_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, Any]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        marker = (str(item.get("kind")), item.get("id"))
        if marker in seen or not item.get("id"):
            continue
        seen.add(marker)
        unique.append(item)
    return unique[:20]


async def stream_reply(
    *,
    provider: Provider,
    adapter: ChatAdapter,
    messages: list[dict[str, Any]],
    toolbox: ToolBox,
    transparency: dict[str, Any],
    cancel: asyncio.Event,
    timeout_s: float = TURN_TIMEOUT_S,
    on_tool_result: Callable[[dict[str, Any]], None] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 ``token`` / ``tool_call`` / ``tool_result`` / ``citation`` / ``done``。

    错误通过 ``LLMError`` / ``TurnTimeout`` / ``TurnCancelled`` 抛给调用方，
    由 API 层转换为 SSE ``error`` 事件并落库。
    """
    conversation = list(messages)
    final_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    tool_calls_used = 0
    usage_total: dict[str, Any] | None = None
    turn_started = time.monotonic()
    # 每个轮次重建一次工具表：模块的安装/授权状态随时可能变化（B2）。
    tools = toolbox.tool_specs()

    async with _Guard(cancel, timeout_s) as guard:
        for _round in range(MAX_TOOL_ROUNDS + 1):
            text_parts: list[str] = []
            pending_calls: list[dict[str, Any]] = []
            attempts = 0
            while True:
                stream = adapter.stream(conversation, tools, cancel)
                emitted = False
                try:
                    while True:
                        try:
                            chunk = await guard.next(stream)
                        except StopAsyncIteration:
                            break
                        kind = chunk.get("type")
                        if kind == "token":
                            text = str(chunk.get("text") or "")
                            if text:
                                emitted = True
                                text_parts.append(text)
                                yield {"event": "token", "data": {"text": text}}
                        elif kind == "tool_calls":
                            pending_calls.extend(chunk.get("calls") or [])
                        elif kind == "usage":
                            usage_total = merge_usage(usage_total, chunk.get("usage"))
                except LLMError as exc:
                    await _close_stream(stream)
                    if (
                        emitted
                        or pending_calls
                        or attempts >= MAX_STREAM_RETRIES
                        or not is_retryable(exc)
                    ):
                        raise
                    attempts += 1
                    text_parts.clear()
                    logger.warning(
                        "llm stream retry provider=%s code=%s attempt=%s",
                        provider.kind,
                        exc.code,
                        attempts,
                    )
                    await _sleep_or_cancel(cancel, RETRY_BACKOFF_S * attempts)
                    continue
                break

            text = "".join(text_parts)
            if not pending_calls:
                if text:
                    final_parts.append(text)
                break

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False),
                        },
                    }
                    for call in pending_calls
                ],
            }
            conversation.append(assistant_message)

            for call in pending_calls:
                call_id = str(call.get("id") or f"call_{uuid7().hex}")
                name = str(call.get("name") or "")
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                yield {
                    "event": "tool_call",
                    "data": {"id": call_id, "name": name, "args": args},
                }

                if tool_calls_used >= MAX_TOOL_CALLS:
                    outcome = {
                        "ok": False,
                        "result": {
                            "error": {
                                "code": "TOOL_LIMIT",
                                "message": "tool call limit reached",
                            }
                        },
                        "summary": "工具调用达到上限",
                        "citations": [],
                    }
                    duration_ms = 0
                else:
                    tool_calls_used += 1
                    started = time.perf_counter()
                    if toolbox.is_module_tool(name):
                        # 模块 RPC 会阻塞到子进程返回；放到线程里，避免卡住整个事件循环。
                        outcome = await asyncio.to_thread(toolbox.execute, name, args)
                    else:
                        outcome = toolbox.execute(name, args)
                    duration_ms = int((time.perf_counter() - started) * 1000)

                event = {
                    "id": call_id,
                    "name": name,
                    "ok": bool(outcome["ok"]),
                    "durationMs": duration_ms,
                    "resultSummary": outcome["summary"],
                }
                if on_tool_result is not None:
                    on_tool_result(
                        {
                            "id": call_id,
                            "name": name,
                            "args": args,
                            "ok": bool(outcome["ok"]),
                            "durationMs": duration_ms,
                            "resultSummary": outcome["summary"],
                        }
                    )
                yield {"event": "tool_result", "data": event}

                for citation in outcome.get("citations") or []:
                    citations.append(citation)
                    yield {"event": "citation", "data": citation}

                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": _truncate_tool_result(outcome["result"]),
                    }
                )

    if not final_parts:
        final_parts.append(
            "工具调用次数已达上限，请缩小问题范围或换一种问法。"
            "以上为数据解读，不构成医学诊断。"
        )

    content = "".join(final_parts).strip()
    citations = _dedupe_citations(citations)
    duration_ms = int((time.monotonic() - turn_started) * 1000)
    yield {
        "event": "done",
        "data": {
            "content": content,
            "citations": citations,
            "toolCalls": tool_calls_used,
            "usage": usage_total,
            "durationMs": duration_ms,
            "transparency": {
                **transparency,
                "toolCalls": tool_calls_used,
                "usage": usage_total,
            },
        },
    }


def format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def error_event(code: str, message: str) -> dict[str, Any]:
    return {"event": "error", "data": {"code": code, "message": message}}


def sanitize_error(kind: str, exc: BaseException, *, status: int | None = None) -> LLMError:
    """公开别名：API 层测试 provider 时复用同一套脱敏规则。"""
    return _sanitize(kind, exc, status=status)


__all__ = [
    "COACH_SYSTEM_PROMPT",
    "MAX_TOOL_CALLS",
    "MAX_TOOL_ROUNDS",
    "SYSTEM_PROMPT",
    "TURN_TIMEOUT_S",
    "ChatAdapter",
    "LLMError",
    "MockAdapter",
    "TurnCancelled",
    "TurnTimeout",
    "adapter_for",
    "approx_tokens",
    "build_context",
    "build_messages",
    "build_transparency",
    "error_event",
    "format_sse",
    "is_retryable",
    "make_usage",
    "merge_usage",
    "stream_reply",
]

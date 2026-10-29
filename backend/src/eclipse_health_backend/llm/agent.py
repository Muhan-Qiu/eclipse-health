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
TURN_TIMEOUT_S = 60.0
REQUEST_TIMEOUT_S = 30.0
MAX_HISTORY_MESSAGES = 20

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
5. 工具只能读取摘要与测量值，读不到波形、备注和成员信息，不要假装能看到。
6. 回答末尾用一句话提醒：以上为数据解读，不构成医学诊断。"""

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
        "localOnly": provider.kind in {"ollama", "mock"},
    }


def build_messages(
    *,
    context_text: str,
    history: list[dict[str, Any]],
    content: str,
    style: str,
) -> list[dict[str, Any]]:
    style_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["brief"])
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


def _sanitize(kind: str, exc: BaseException, *, status: int | None = None) -> LLMError:
    """只保留 provider 类型与 HTTP 状态；绝不透传原始异常文本。"""
    if status is not None:
        return LLMError(f"{kind}_http_error", f"{kind} request failed (HTTP {status})")
    if isinstance(exc, httpx.TimeoutException):
        return LLMError("timeout", f"{kind} request timed out")
    if isinstance(exc, httpx.HTTPError):
        return LLMError(f"{kind}_network_error", f"{kind} connection failed")
    return LLMError(f"{kind}_error", f"{kind} request failed ({type(exc).__name__})")


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


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"id": f"call_{uuid7().hex[:12]}", "name": name, "args": args}


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
        if tools:
            payload["tools"] = tools

        calls: list[dict[str, Any]] = []
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
                                "id": f"call_{uuid7().hex[:12]}",
                                "name": str(name),
                                "args": args if isinstance(args, dict) else _parse_arguments(args),
                            }
                        )
                    if chunk.get("done"):
                        break
        except LLMError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 统一脱敏
            raise _sanitize("ollama", exc) from None

        if calls:
            yield {"type": "tool_calls", "calls": calls}


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
            "model": f"{self.provider.kind}/{self.provider.model}",
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

        calls: dict[int, dict[str, Any]] = {}
        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                if cancel.is_set():
                    return
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
            raise _sanitize(self.provider.kind, exc, status=status) from None

        ordered = [calls[index] for index in sorted(calls)]
        if ordered:
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": item["id"] or f"call_{uuid7().hex[:12]}",
                        "name": item["name"],
                        "args": _parse_arguments(item["arguments"]),
                    }
                    for item in ordered
                    if item["name"]
                ],
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

    async with _Guard(cancel, timeout_s) as guard:
        for _round in range(MAX_TOOL_ROUNDS + 1):
            stream = adapter.stream(conversation, TOOL_SPECS, cancel)
            text_parts: list[str] = []
            pending_calls: list[dict[str, Any]] = []
            while True:
                try:
                    chunk = await guard.next(stream)
                except StopAsyncIteration:
                    break
                kind = chunk.get("type")
                if kind == "token":
                    text = str(chunk.get("text") or "")
                    if text:
                        text_parts.append(text)
                        yield {"event": "token", "data": {"text": text}}
                elif kind == "tool_calls":
                    pending_calls.extend(chunk.get("calls") or [])

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
                call_id = str(call.get("id") or f"call_{uuid7().hex[:12]}")
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
    yield {
        "event": "done",
        "data": {
            "content": content,
            "citations": citations,
            "toolCalls": tool_calls_used,
            "transparency": {**transparency, "toolCalls": tool_calls_used},
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
    "stream_reply",
]

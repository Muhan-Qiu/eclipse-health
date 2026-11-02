"""导入 Agent 的工具循环（SSE 事件）。

与 ``llm.agent.stream_reply`` 同构，但工具集、预算与系统提示都只服务数据导入：
24 次工具调用、整轮 300 s、无网络、候选必须带证据。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, Self

from ..domain.ids import uuid7
from ..llm import agent as llm_agent
from ..llm.agent import ChatAdapter
from ..llm.providers import Provider
from . import limits
from .tools import TOOL_SPECS, ToolBox

logger = logging.getLogger(__name__)

MAX_ROUNDS = limits.MAX_TOOL_CALLS + 2

KIND_HINT = (
    "steps, heart-rate, resting-heart-rate, sleep, body-mass, blood-pressure, spo2, "
    "stress, workout, respiratory-rate, body-temperature, blood-glucose, hrv, ecg, body"
)

SYSTEM_PROMPT = f"""你是 eclipse health 的“数据导入 Agent”。用户上传了一份健康数据导出文件，
你要在受限沙箱里用 Python 解析它，并把可验证的健康记录作为候选提交。

强制规则：
1. 先调用 list_files，了解本次文件；不要假设文件格式。
2. 只能访问本次 session 的文件。所有路径都是相对路径；不要尝试访问系统目录、数据库或网络。
3. 解析二进制/复杂格式（PDF、XLSX、HTML、ZIP、XML、CSV）时，写 Python 脚本并用 run_python 执行。
   沙箱内可 `import eh_import_helpers`，提供 read_csv_rows / read_json / read_xml / iter_xml /
   read_html_tables / read_xlsx_rows / read_pdf_pages / extract_zip_safe / read_text。
4. 不要猜数值。每个候选必须带 evidence：来源文件 + 行号/页码/locator/原文片段，以及 confidence。
5. CSV 列名不固定：按语义匹配列（心率、时间、收缩压……），不要写死列序。
6. 支持的 kind：{KIND_HINT}。单位用 UCUM：count、count/min、kg、mm[Hg]、%、Cel、
   mg/dL、mmol/L、ms、mV、1。数值必须落在合理范围；不确定就不要提交。
7. 睡眠/运动必须有 endAt；血压 value 是 {{systolic, diastolic}}；HRV value 是 {{metric, value}}；
   body 是身体成分对象。
8. PDF 或图片里的心电图波形**无法可靠还原为采样点**：只提取报告中的数值/结论，绝不创建
   ecg 记录。只有文件里确实有采样数据（CSV/HTML/XLSX/JSON 中的 time+voltage、
   sample+value、timestamp+mv 等成对列，或输出里的采样表）时，才把采样写成
   两列（time 或 sample，voltage）写到 output/ 下的 CSV，waveform.file 写相对 output/ 的文件名（如 ecg.csv），并在候选里提供：
   "waveform":{{"file":"ecg.csv","format":"csv","column":"voltage",
   "timeColumn":"time","samplingRate":<Hz>,"unit":"mV","lead":"I"}}。
   采样率可由 time 列间隔推断；无法推断时写 samplingRate=null 让用户确认。
9. 用 propose_records 分批提交（单次 ≤1000 条），根据返回的 rejected/issues 修正后重试。
   每条候选必须严格是这个形状（多一个字段都会被拒绝）：
   {{"kind":"heart-rate","value":62,"unit":"count/min",
    "startAt":"2026-10-01T08:00:00+08:00","endAt":null,
    "source":{{"kind":"app","app":"Samsung Health"}},
    "evidence":{{"file":"export.csv","line":2,"snippet":"2026-10-01,08:00,62"}},
    "confidence":0.95}}
   source 只能是 {{"kind","app","device","manufacturer"}}，kind ∈ app/device/manual/unknown；
   startAt/endAt 必须带时区；evidence.file 必须是本次上传文件。
   先用 1 条记录试提交，确认返回 accepted>0 后再批量提交，避免连续被 schema 拒绝。
10. 完成后必须调用 finish，用中文总结：写入了多少条、跳过了什么、哪些值不确定。
11. 不联网、不启动其他进程、不读取本次上传文件以外的内容。
"""


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #


class AgentCancelled(Exception):
    pass


class AgentTimeout(Exception):
    pass


class _Guard:
    """整轮截止时间 + 取消事件；与 llm.agent._Guard 同构，保持行为一致。"""

    def __init__(self, cancel: asyncio.Event, timeout_s: float) -> None:
        self._cancel = cancel
        self._deadline = time.monotonic() + timeout_s
        self._cancel_task: asyncio.Future[bool] | None = None

    @property
    def deadline(self) -> float:
        return self._deadline

    async def __aenter__(self) -> Self:
        self._cancel_task = asyncio.ensure_future(self._cancel.wait())
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._cancel_task is not None:
            self._cancel_task.cancel()

    async def next(self, iterator: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTimeout
        if self._cancel.is_set():
            raise AgentCancelled
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
            raise AgentCancelled
        raise AgentTimeout


# --------------------------------------------------------------------------- #
# Mock provider
# --------------------------------------------------------------------------- #


class ImportMockAdapter:
    """确定性演示：list_files → read_text_file → finish。

    不依赖网络，也不猜数值；只用于验证 SSE 与工具链路。真实解析请配置 Ollama/云端模型。
    """

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

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
        if "list_files" not in called:
            yield {"type": "tool_calls", "calls": [_call("list_files", {})]}
            return
        first = _first_text_file(messages)
        if first and "read_text_file" not in called:
            yield {
                "type": "tool_calls",
                "calls": [_call("read_text_file", {"path": first, "limit": 4000})],
            }
            return
        if "finish" not in called:
            text = "Mock provider 已完成文件检查。未生成候选记录；请配置真实模型解析内容。"
            if cancel.is_set():
                return
            yield {"type": "token", "text": text}
            yield {"type": "tool_calls", "calls": [_call("finish", {"summary": text})]}
            return
        if cancel.is_set():
            return
        yield {"type": "token", "text": "任务结束。"}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"id": f"call_{uuid7().hex}", "name": name, "args": args}


def _first_text_file(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("name") != "list_files":
            continue
        try:
            payload = json.loads(message.get("content") or "{}")
        except (TypeError, ValueError):
            return None
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("kind") in {"text", "csv", "json", "xml", "html"}:
                return str(item.get("name") or "") or None
        return None
    return None


def make_adapter(provider: Provider, api_key: str | None) -> ChatAdapter | ImportMockAdapter:
    if provider.kind == "mock":
        return ImportMockAdapter(provider)
    return llm_agent.adapter_for(provider, api_key)


# --------------------------------------------------------------------------- #
# 消息
# --------------------------------------------------------------------------- #


def _files_block(meta: dict[str, Any]) -> str:
    lines: list[str] = []
    for entry in (meta.get("files") or [])[: limits.MAX_FILES_IN_PROMPT]:
        if not isinstance(entry, dict):
            continue
        sha = str(entry.get("sha256") or "")
        lines.append(
            f"- {entry.get('name')} ({entry.get('size')} bytes, {entry.get('kind')}, {sha[:23]})"
        )
    remaining = max(0, len(meta.get("files") or []) - limits.MAX_FILES_IN_PROMPT)
    if remaining:
        lines.append(f"- … 另有 {remaining} 个文件（调用 list_files 查看）")
    return "\n".join(lines) or "- （没有文件）"


def build_messages(meta: dict[str, Any], instructions: str | None) -> list[dict[str, Any]]:
    user = (
        "本次上传文件：\n"
        f"{_files_block(meta)}\n\n"
        f"用户补充说明：{instructions.strip() if instructions else '无'}\n\n"
        "请开始解析；先 list_files，再按需写脚本。完成后调用 finish。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _tool_content(result: dict[str, Any]) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= limits.MAX_TOOL_RESULT_BYTES:
        return text
    return json.dumps(
        {
            "truncated": True,
            "bytes": len(text),
            "preview": text[: limits.MAX_TOOL_RESULT_BYTES - 120],
        },
        ensure_ascii=False,
    )


def _provider_view(provider: Provider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "kind": provider.kind,
        "label": provider.label,
        "model": provider.model,
        "localOnly": provider.kind in {"ollama", "mock"},
    }


def _status(
    provider: Provider,
    meta: dict[str, Any],
    *,
    tool_calls: int,
    started: float,
    phase: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "provider": _provider_view(provider),
        "files": [entry.get("name") for entry in meta.get("files") or [] if isinstance(entry, dict)],
        "limits": {
            "maxToolCalls": limits.MAX_TOOL_CALLS,
            "maxTurnSeconds": int(limits.MAX_TURN_SECONDS),
            "network": False,
        },
        "toolCalls": tool_calls,
        "elapsedMs": int((time.monotonic() - started) * 1000),
        "network": False,
    }


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #


async def stream_import_agent(
    *,
    provider: Provider,
    adapter: ChatAdapter | ImportMockAdapter,
    session_id: str,
    meta: dict[str, Any],
    instructions: str | None,
    cancel: asyncio.Event,
) -> AsyncIterator[dict[str, Any]]:
    """产出 ``status/token/tool_call/tool_result/preview/done``。

    调用方负责把异常转成 SSE ``error`` 并更新 session 状态。
    """
    started = time.monotonic()
    toolbox = ToolBox(session_id, meta, cancel=cancel)
    messages = build_messages(meta, instructions)
    tools = list(TOOL_SPECS)
    tool_calls_used = 0
    last_text = ""
    finished = False

    async with _Guard(cancel, limits.MAX_TURN_SECONDS) as guard:
        toolbox.deadline = guard.deadline
        yield {
            "event": "status",
            "data": _status(provider, meta, tool_calls=0, started=started, phase="running"),
        }

        for _round in range(MAX_ROUNDS):
            text_parts: list[str] = []
            pending: list[dict[str, Any]] = []
            stream = adapter.stream(messages, tools, cancel)
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
                            text_parts.append(text)
                            yield {"event": "token", "data": {"text": text}}
                    elif kind == "tool_calls":
                        pending.extend(chunk.get("calls") or [])
            except BaseException:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    try:
                        await close()
                    except Exception:  # noqa: BLE001, S110 - 连接可能已断开
                        pass
                raise

            text = "".join(text_parts)
            if text:
                last_text = text
            if not pending:
                break

            messages.append(
                {
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
                        for call in pending
                    ],
                }
            )

            for index, call in enumerate(pending):
                call_id = str(call.get("id") or f"call_{uuid7().hex}")
                name = str(call.get("name") or "")
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                yield {
                    "event": "tool_call",
                    "data": {"id": call_id, "name": name, "args": args, "index": index},
                }

                if tool_calls_used >= limits.MAX_TOOL_CALLS:
                    outcome = {
                        "ok": False,
                        "result": {
                            "error": {
                                "code": "TOOL_LIMIT",
                                "message": "tool call limit reached",
                            }
                        },
                        "summary": "工具调用达到上限",
                    }
                    duration_ms = 0
                else:
                    tool_calls_used += 1
                    tool_started = time.perf_counter()
                    outcome_obj = await asyncio.to_thread(toolbox.execute, name, args)
                    duration_ms = int((time.perf_counter() - tool_started) * 1000)
                    outcome = {
                        "ok": outcome_obj.ok,
                        "result": outcome_obj.result,
                        "summary": outcome_obj.summary,
                    }
                    meta["toolCalls"] = tool_calls_used

                event: dict[str, Any] = {
                    "id": call_id,
                    "name": name,
                    "ok": bool(outcome["ok"]),
                    "durationMs": duration_ms,
                    "resultSummary": outcome["summary"],
                }
                error = outcome["result"].get("error")
                if not outcome["ok"] and isinstance(error, dict):
                    event["error"] = error
                yield {"event": "tool_result", "data": event}

                if name == "propose_records" and outcome["ok"]:
                    result = outcome["result"]
                    yield {
                        "event": "preview",
                        "data": {
                            "count": int(result.get("accepted") or 0),
                            "total": int(result.get("proposalCount") or 0),
                            "items": result.get("items") or [],
                            "issues": result.get("issues") or [],
                        },
                    }
                if name == "finish" and toolbox.finished:
                    finished = True

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": _tool_content(outcome["result"]),
                    }
                )
                yield {
                    "event": "status",
                    "data": _status(
                        provider,
                        meta,
                        tool_calls=tool_calls_used,
                        started=started,
                        phase="tool",
                    ),
                }
                if finished:
                    break

            if finished:
                break

    summary = toolbox.finish_summary or last_text.strip() or "已完成解析"
    meta["summary"] = summary
    meta["toolCalls"] = tool_calls_used
    yield {
        "event": "done",
        "data": {
            "summary": summary,
            "proposalCount": int(meta.get("proposalCount") or 0),
            "toolCalls": tool_calls_used,
            "durationMs": int((time.monotonic() - started) * 1000),
            "status": "ready",
        },
    }


__all__ = [
    "SYSTEM_PROMPT",
    "AgentCancelled",
    "AgentTimeout",
    "ImportMockAdapter",
    "build_messages",
    "make_adapter",
    "stream_import_agent",
]

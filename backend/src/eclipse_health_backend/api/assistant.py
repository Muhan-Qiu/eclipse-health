"""助手 API（B3-04）：provider、会话、消息（SSE）、透明面板。

安全边界：

- provider 响应只返回 ``configured``，从不返回 key；
- 工具与上下文都限定在当前成员，越权一律 ``*_not_found``；
- SSE 事件与落库只保存摘要，不保存工具完整返回值。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import assistant_repo
from ..db.base import engine, session_scope
from ..db.repositories import ensure_default_member, get_record_row
from ..domain.errors import ApiError, ConflictError, InvalidInputError, NotFoundError, not_found
from ..llm import agent
from ..llm.providers import (
    Provider,
    ProviderError,
    get_provider_store,
)
from ..llm.tools import ToolBox
from .deps import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

StyleName = Literal["brief", "detailed", "doctor"]
STYLES: tuple[str, ...] = ("brief", "detailed", "doctor")


# --------------------------------------------------------------------------- #
# 请求 / 响应模型
# --------------------------------------------------------------------------- #


class ProviderIn(BaseModel):
    kind: Literal["openai", "anthropic", "ollama", "mock"] | None = None
    label: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    baseUrl: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None
    apiKey: str | None = Field(default=None, max_length=4096)
    clearKey: bool = False


class ProviderTestResult(BaseModel):
    ok: bool
    providerId: str
    kind: str
    model: str
    latencyMs: int | None = None
    message: str


class SessionIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    providerId: str | None = Field(default=None, max_length=64)
    style: StyleName = "brief"
    recordId: str | None = Field(default=None, max_length=64)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    style: StyleName = "brief"
    providerId: str = Field(min_length=1, max_length=64)
    recordId: str | None = Field(default=None, max_length=64)
    includeNotes: bool = False


class MessageListOut(BaseModel):
    items: list[dict[str, Any]]


# --------------------------------------------------------------------------- #
# 公共助手
# --------------------------------------------------------------------------- #


def _translate(exc: ProviderError) -> ApiError:
    if exc.status_code == 404:
        return NotFoundError(exc.message, code=exc.code)
    if exc.status_code == 409:
        return ConflictError(exc.message, code=exc.code)
    if exc.status_code >= 500:
        return ApiError(exc.message, code=exc.code, status_code=exc.status_code)
    return InvalidInputError(exc.message, code=exc.code)


def _current_member_id(session: Session) -> str:
    return ensure_default_member(session).id


def _require_session(session: Session, session_id: str, member_id: str) -> Any:
    row = assistant_repo.get_session_row(session, session_id)
    if row is None or row.member_id != member_id:
        raise not_found("assistant_session", session_id)
    return row


def _require_record(session: Session, record_id: str, member_id: str) -> Any:
    row = get_record_row(session, record_id)
    if row is None or row.deleted_at is not None or row.member_id != member_id:
        raise not_found("record", record_id)
    return row


def _require_provider(provider_id: str) -> Provider:
    try:
        provider = get_provider_store().get(provider_id)
    except ProviderError as exc:
        raise _translate(exc) from exc
    if not provider.enabled:
        raise ConflictError("provider is disabled", code="provider_disabled")
    return provider


def _message_payload(row: Any, calls: list[Any]) -> dict[str, Any]:
    payload = assistant_repo.message_to_dict(row, calls)
    data = row.data or {}
    payload["transparency"] = data.get("transparency")
    return payload


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #


@router.get("/providers", summary="provider 列表（不含任何 key）")
def list_providers() -> dict[str, Any]:
    providers = get_provider_store().list()
    return {"items": [provider.to_public() for provider in providers]}


@router.put("/providers/{provider_id}", summary="新建或更新 provider")
def upsert_provider(provider_id: str, payload: ProviderIn) -> dict[str, Any]:
    fields = payload.model_fields_set
    body = payload.model_dump(exclude_unset=True, exclude={"apiKey", "clearKey"})
    # apiKey 未出现在请求里时保持原值；显式传空字符串表示清除。
    api_key = payload.apiKey if "apiKey" in fields else None
    try:
        provider = get_provider_store().upsert(
            provider_id,
            body,
            api_key=api_key,
            clear_key=payload.clearKey,
        )
    except ProviderError as exc:
        raise _translate(exc) from exc
    return provider.to_public()


@router.delete("/providers/{provider_id}", status_code=204, summary="删除 provider")
def delete_provider(provider_id: str) -> None:
    try:
        get_provider_store().delete(provider_id)
    except ProviderError as exc:
        raise _translate(exc) from exc


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderTestResult,
    summary="测试 provider 连通性（错误信息只含类型与 HTTP 状态）",
)
async def test_provider(provider_id: str) -> ProviderTestResult:
    provider = _require_provider(provider_id)
    started = time.perf_counter()
    try:
        if provider.kind == "mock":
            message = "mock provider 始终可用"
        elif provider.kind == "ollama":
            message = await _test_ollama(provider)
        else:
            message = await _test_litellm(provider)
    except ProviderError as exc:
        raise _translate(exc) from exc
    except agent.LLMError as exc:
        return ProviderTestResult(
            ok=False,
            providerId=provider.id,
            kind=provider.kind,
            model=provider.model,
            latencyMs=int((time.perf_counter() - started) * 1000),
            message=exc.message,
        )
    latency = int((time.perf_counter() - started) * 1000)
    logger.info("provider test ok id=%s kind=%s latency_ms=%s", provider.id, provider.kind, latency)
    return ProviderTestResult(
        ok=True,
        providerId=provider.id,
        kind=provider.kind,
        model=provider.model,
        latencyMs=latency,
        message=message,
    )


async def _test_ollama(provider: Provider) -> str:
    base = (provider.base_url or "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": provider.model,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "options": {"num_predict": 4},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{base}/api/chat", json=payload)
    except httpx.TimeoutException:
        raise agent.LLMError("timeout", "ollama request timed out") from None
    except httpx.HTTPError:
        raise agent.LLMError("ollama_network_error", "ollama connection failed") from None
    if response.status_code >= 400:
        raise agent.LLMError("ollama_http_error", f"ollama request failed (HTTP {response.status_code})")
    return "Ollama 连接成功"


async def _test_litellm(provider: Provider) -> str:
    if provider.needs_key:
        key = get_provider_store().resolve_api_key(provider)
        if not key:
            raise ConflictError(
                "provider API key is not configured", code="missing_api_key"
            )
    else:  # pragma: no cover - 当前所有非本地 provider 都需要 key
        key = None
    try:
        import litellm
    except ImportError as exc:  # pragma: no cover
        raise agent.LLMError("litellm_missing", "LiteLLM is not installed") from exc
    kwargs: dict[str, Any] = {
        "model": f"{provider.kind}/{provider.model}",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 4,
        "timeout": 10,
    }
    if key:
        kwargs["api_key"] = key
    if provider.base_url and provider.kind == "openai":
        kwargs["api_base"] = provider.base_url
    try:
        await litellm.acompletion(**kwargs)
    except BaseException as exc:  # noqa: BLE001 - 统一脱敏
        status = getattr(exc, "status_code", None)
        raise agent.sanitize_error(provider.kind, exc, status=status) from None
    return "连接成功"


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


@router.get("/sessions", summary="会话列表（按更新时间倒序）")
def list_sessions(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    member_id = _current_member_id(session)
    rows = assistant_repo.list_session_rows(session, member_id, limit=limit, offset=offset)
    items = [
        assistant_repo.session_to_dict(
            row, message_count=assistant_repo.count_messages(session, row.id)
        )
        for row in rows
    ]
    return {"items": items}


@router.post("/sessions", status_code=201, summary="新建会话")
def create_session(payload: SessionIn, session: SessionDep) -> dict[str, Any]:
    member_id = _current_member_id(session)
    if payload.recordId:
        _require_record(session, payload.recordId, member_id)
    row = assistant_repo.create_session(
        session,
        member_id=member_id,
        title=payload.title or "新会话",
        provider_id=payload.providerId,
        style=payload.style,
        record_id=payload.recordId,
    )
    return assistant_repo.session_to_dict(row)


@router.get("/sessions/{session_id}", summary="会话详情（不含消息）")
def get_session(session_id: str, session: SessionDep) -> dict[str, Any]:
    member_id = _current_member_id(session)
    row = _require_session(session, session_id, member_id)
    return assistant_repo.session_to_dict(
        row, message_count=assistant_repo.count_messages(session, session_id)
    )


@router.delete("/sessions/{session_id}", status_code=204, summary="删除会话及其消息")
def delete_session(session_id: str, session: SessionDep) -> None:
    member_id = _current_member_id(session)
    _require_session(session, session_id, member_id)
    assistant_repo.delete_session(session, session_id)


@router.get("/sessions/{session_id}/messages", response_model=MessageListOut)
def list_messages(
    session_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessageListOut:
    member_id = _current_member_id(session)
    _require_session(session, session_id, member_id)
    rows = assistant_repo.list_message_rows(session, session_id, limit=limit, offset=offset)
    items = [
        _message_payload(row, assistant_repo.list_tool_calls(session, row.id)) for row in rows
    ]
    return MessageListOut(items=items)


@router.get(
    "/messages/{message_id}/transparency",
    summary="透明面板：这条回答发送了什么",
)
def get_transparency(message_id: str, session: SessionDep) -> dict[str, Any]:
    member_id = _current_member_id(session)
    row = assistant_repo.get_message_row(session, message_id)
    if row is None:
        raise not_found("assistant_message", message_id)
    parent = assistant_repo.get_session_row(session, row.session_id)
    if parent is None or parent.member_id != member_id:
        raise not_found("assistant_message", message_id)
    transparency = assistant_repo.transparency_of(row)
    if transparency is None:
        raise NotFoundError(
            "this message has no transparency record",
            code="transparency_not_available",
        )
    return transparency


# --------------------------------------------------------------------------- #
# SSE：发送消息
# --------------------------------------------------------------------------- #


@router.post(
    "/sessions/{session_id}/messages",
    summary="发送消息（SSE：token/tool_call/tool_result/citation/done/error）",
    response_class=StreamingResponse,
)
async def send_message(
    session_id: str,
    payload: MessageIn,
    request: Request,
    session: SessionDep,
) -> StreamingResponse:
    member_id = _current_member_id(session)
    session_row = _require_session(session, session_id, member_id)
    provider = _require_provider(payload.providerId)
    if provider.needs_key and not provider.key_ref:
        raise ConflictError(
            "provider API key is not configured", code="missing_api_key"
        )
    if payload.recordId:
        _require_record(session, payload.recordId, member_id)

    style = payload.style if payload.style in STYLES else "brief"
    history = assistant_repo.history_for_prompt(session, session_id)
    is_first_user_message = not any(item["role"] == "user" for item in history)

    user_row = assistant_repo.add_message(
        session,
        session_id=session_id,
        role=assistant_repo.ROLE_USER,
        content=payload.content.strip(),
        status=assistant_repo.STATUS_COMPLETED,
        data={"style": style, "providerId": provider.id},
    )
    assistant_row = assistant_repo.add_message(
        session,
        session_id=session_id,
        role=assistant_repo.ROLE_ASSISTANT,
        content="",
        status=assistant_repo.STATUS_STREAMING,
        data={"style": style, "providerId": provider.id},
    )
    assistant_repo.touch_session(
        session,
        session_row,
        title=payload.content.strip()[:24] if is_first_user_message else None,
        provider_id=provider.id,
        style=style,
        record_id=payload.recordId or session_row.record_id,
        has_notes=payload.includeNotes or None,
        commit=True,
    )
    assistant_id = assistant_row.id
    user_id = user_row.id

    return StreamingResponse(
        _sse_events(
            request=request,
            session_id=session_id,
            member_id=member_id,
            provider=provider,
            assistant_id=assistant_id,
            user_id=user_id,
            payload=payload,
            style=style,
            history=history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭 Nginx/桌面代理的缓冲，token 才能逐条到达
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_events(
    *,
    request: Request,
    session_id: str,
    member_id: str,
    provider: Provider,
    assistant_id: str,
    user_id: str,
    payload: MessageIn,
    style: str,
    history: list[dict[str, Any]],
) -> AsyncIterator[str]:
    cancel = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, cancel))
    content_parts: list[str] = []
    final: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    cancelled = False

    # 工具读取用只读会话；SQLite WAL 下长事务只读不会阻塞写入。
    tool_session = Session(engine)
    try:
        try:
            context = agent.build_context(
                tool_session,
                member_id=member_id,
                record_id=payload.recordId,
                include_notes=payload.includeNotes,
            )
            messages = agent.build_messages(
                context_text=context["contextText"],
                history=[item for item in history if item["role"] in {"user", "assistant"}],
                content=payload.content.strip(),
                style=style,
            )
            transparency = agent.build_transparency(
                provider, context=context, messages=messages
            )
            adapter = agent.adapter_for(provider, _resolve_key(provider))
            toolbox = ToolBox(tool_session, member_id)

            def persist_tool(call: dict[str, Any]) -> None:
                with session_scope() as db:
                    assistant_repo.add_tool_call(
                        db,
                        message_id=assistant_id,
                        session_id=session_id,
                        name=call["name"],
                        args=call["args"],
                        result_summary=call["resultSummary"],
                        ok=call["ok"],
                        duration_ms=call["durationMs"],
                        tool_call_id=call["id"],
                        commit=True,
                    )

            async for event in agent.stream_reply(
                provider=provider,
                adapter=adapter,
                messages=messages,
                toolbox=toolbox,
                transparency=transparency,
                cancel=cancel,
                on_tool_result=persist_tool,
            ):
                name = event["event"]
                if name == "token":
                    content_parts.append(str(event["data"].get("text") or ""))
                elif name == "done":
                    final = event["data"]
                elif name == "error":
                    failure = event["data"]
                yield agent.format_sse(name, event["data"])
        except agent.TurnCancelled:
            cancelled = True
        except agent.TurnTimeout:
            failure = {"code": "timeout", "message": "本轮对话超过 60 秒，已停止"}
            yield agent.format_sse("error", failure)
        except agent.LLMError as exc:
            failure = {"code": exc.code, "message": exc.message}
            yield agent.format_sse("error", failure)
        except ProviderError as exc:
            failure = {"code": exc.code, "message": "provider is not available"}
            yield agent.format_sse("error", failure)
        except Exception:
            logger.exception("assistant turn failed session=%s", session_id)
            failure = {"code": "internal_error", "message": "助手执行失败，请稍后重试"}
            yield agent.format_sse("error", failure)
    except (GeneratorExit, asyncio.CancelledError):
        cancelled = True
        raise
    finally:
        watcher.cancel()
        tool_session.close()
        _finalize_message(
            assistant_id,
            content="".join(content_parts),
            final=final,
            failure=failure,
            cancelled=cancelled,
        )
        try:
            with session_scope() as db:
                row = assistant_repo.get_session_row(db, session_id)
                if row is not None:
                    assistant_repo.touch_session(db, row, commit=True)
        except Exception:
            logger.exception("assistant session touch failed session=%s", session_id)
        logger.info(
            "assistant turn done session=%s user=%s assistant=%s cancelled=%s",
            session_id,
            user_id,
            assistant_id,
            cancelled,
        )

    if cancelled:
        yield agent.format_sse(
            "done",
            {
                "content": "".join(content_parts),
                "citations": [],
                "toolCalls": 0,
                "cancelled": True,
            },
        )


async def _watch_disconnect(request: Request, cancel: asyncio.Event) -> None:
    try:
        while not cancel.is_set():
            if await request.is_disconnected():
                cancel.set()
                return
            try:
                await asyncio.wait_for(cancel.wait(), timeout=0.5)
            except TimeoutError:
                continue
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - 断连探测失败就放弃探测
        return


def _resolve_key(provider: Provider) -> str | None:
    if not provider.needs_key:
        return None
    try:
        return get_provider_store().resolve_api_key(provider)
    except ProviderError as exc:
        raise agent.LLMError("key_unavailable", "stored API key could not be decrypted") from exc


def _finalize_message(
    message_id: str,
    *,
    content: str,
    final: dict[str, Any] | None,
    failure: dict[str, Any] | None,
    cancelled: bool,
) -> None:
    try:
        with session_scope() as db:
            row = assistant_repo.get_message_row(db, message_id)
            if row is None:
                return
            data = dict(row.data or {})
            if final is not None:
                data["citations"] = final.get("citations") or []
                data["transparency"] = final.get("transparency")
                if cancelled:
                    assistant_repo.update_message(
                        db,
                        row,
                        content=content,
                        status=assistant_repo.STATUS_CANCELLED,
                        data=data,
                        commit=False,
                    )
                else:
                    assistant_repo.update_message(
                        db,
                        row,
                        content=final.get("content") or content,
                        status=assistant_repo.STATUS_COMPLETED,
                        data=data,
                        commit=False,
                    )
            elif cancelled:
                assistant_repo.update_message(
                    db,
                    row,
                    content=content,
                    status=assistant_repo.STATUS_CANCELLED,
                    data=data,
                    commit=False,
                )
            elif failure is not None:
                data["error"] = failure
                assistant_repo.update_message(
                    db,
                    row,
                    content=content,
                    status=assistant_repo.STATUS_ERROR,
                    data=data,
                    commit=False,
                )
            else:
                data["error"] = {"code": "interrupted", "message": "stream ended unexpectedly"}
                assistant_repo.update_message(
                    db,
                    row,
                    content=content,
                    status=assistant_repo.STATUS_ERROR,
                    data=data,
                    commit=False,
                )
    except Exception:
        logger.exception("assistant message finalize failed id=%s", message_id)


__all__ = ["router"]

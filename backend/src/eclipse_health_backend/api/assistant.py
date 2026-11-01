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
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import assistant_repo
from ..db.base import engine, session_scope
from ..db.repositories import ensure_default_member, get_record_row
from ..domain.common import utc_now
from ..domain.errors import ApiError, ConflictError, InvalidInputError, NotFoundError, not_found
from ..llm import agent, session_export
from ..llm.provider_presets import list_presets
from ..llm.providers import (
    Provider,
    ProviderError,
    get_provider_store,
)
from ..llm.tools import ToolBox
from ..llm.turns import get_turn_registry
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
    presetId: str | None = Field(default=None, max_length=64)
    litellmProvider: str | None = Field(default=None, max_length=40)
    needsKey: bool | None = None
    local: bool | None = None
    apiKey: str | None = Field(default=None, max_length=4096)
    clearKey: bool = False


class ProviderTestResult(BaseModel):
    ok: bool
    providerId: str
    kind: str
    model: str
    latencyMs: int | None = None
    message: str
    # 能力探测：模型是否已安装、是否声明支持 tool calling；无法判断时为 null。
    available: bool | None = None
    supportsTools: bool | None = None
    models: list[str] = []


class SessionIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    providerId: str | None = Field(default=None, max_length=64)
    style: StyleName = "brief"
    recordId: str | None = Field(default=None, max_length=64)


class SessionPatch(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    style: StyleName = "brief"
    providerId: str = Field(min_length=1, max_length=64)
    recordId: str | None = Field(default=None, max_length=64)
    includeNotes: bool = False


class MessageListOut(BaseModel):
    items: list[dict[str, Any]]
    total: int = 0
    limit: int = 200
    offset: int = 0
    hasMore: bool = False


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


@router.get("/provider-presets", summary="服务商预设（不含任何 key）")
def list_provider_presets() -> dict[str, Any]:
    return {"items": list_presets()}


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
            probe = _Probe(
                ok=True,
                message="Mock 始终可用，支持工具调用",
                available=True,
                supports_tools=True,
            )
        elif provider.kind == "ollama":
            probe = await _test_ollama(provider)
        else:
            probe = await _test_litellm(provider)
    except ProviderError as exc:
        raise _translate(exc) from exc
    except agent.LLMError as exc:
        probe = _Probe(ok=False, message=exc.message)
    latency = probe.latency_ms
    if latency is None:
        latency = int((time.perf_counter() - started) * 1000)
    if probe.ok:
        logger.info(
            "provider test ok id=%s kind=%s model=%s latency_ms=%s tools=%s",
            provider.id,
            provider.kind,
            provider.model,
            latency,
            probe.supports_tools,
        )
    else:
        logger.info(
            "provider test failed id=%s kind=%s code_message=%s",
            provider.id,
            provider.kind,
            probe.message[:120],
        )
    return ProviderTestResult(
        ok=probe.ok,
        providerId=provider.id,
        kind=provider.kind,
        model=provider.model,
        latencyMs=latency,
        message=probe.message,
        available=probe.available,
        supportsTools=probe.supports_tools,
        models=probe.models,
    )


class _Probe:
    """一次能力探测的结果；``latency_ms`` 只计模型调用本身。"""

    def __init__(
        self,
        *,
        ok: bool,
        message: str,
        available: bool | None = None,
        supports_tools: bool | None = None,
        models: list[str] | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self.ok = ok
        self.message = message
        self.available = available
        self.supports_tools = supports_tools
        self.models = models or []
        self.latency_ms = latency_ms


def _model_present(model: str, names: list[str]) -> bool:
    """Ollama 不带 tag 时等价于 ``:latest``，不做模糊匹配以免误报可用。"""
    if model in names:
        return True
    return ":" not in model and f"{model}:latest" in names


async def _test_ollama(
    provider: Provider, *, transport: httpx.AsyncBaseTransport | None = None
) -> _Probe:
    base = (provider.base_url or "http://127.0.0.1:11434").rstrip("/")
    # 冷加载 9B 级模型可能要 30 s+；探测是用户主动点击，可以等。
    try:
        async with httpx.AsyncClient(timeout=60.0, transport=transport) as client:
            try:
                tags = await client.get(f"{base}/api/tags")
            except httpx.TimeoutException:
                raise agent.LLMError("timeout", "Ollama 连接超时") from None
            except httpx.HTTPError:
                raise agent.LLMError(
                    "ollama_network_error", "无法连接 Ollama，请确认本地服务已启动"
                ) from None
            if tags.status_code >= 400:
                raise agent.sanitize_error(
                    "ollama", RuntimeError("http"), status=tags.status_code
                )
            try:
                payload = tags.json()
            except ValueError:
                payload = {}
            names = [
                str(item.get("name"))
                for item in (payload.get("models") or [])
                if isinstance(item, dict) and item.get("name")
            ]
            if not _model_present(provider.model, names):
                hint = "、".join(names[:6]) if names else "（没有已安装模型）"
                return _Probe(
                    ok=False,
                    available=False,
                    models=names[:20],
                    message=f"模型 {provider.model} 未安装；本地可用：{hint}",
                )

            supports_tools: bool | None = None
            try:
                show = await client.post(
                    f"{base}/api/show", json={"model": provider.model}
                )
                if show.status_code < 400:
                    capabilities = show.json().get("capabilities")
                    if isinstance(capabilities, list):
                        supports_tools = "tools" in capabilities
            except (httpx.HTTPError, ValueError):
                # /api/show 在旧版本上可能不存在，能力保持未知，不影响主探测。
                supports_tools = None

            started = time.perf_counter()
            try:
                chat = await client.post(
                    f"{base}/api/chat",
                    json={
                        "model": provider.model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "stream": False,
                        "think": False,
                        "options": {"num_predict": 4, "temperature": 0},
                    },
                )
            except httpx.TimeoutException:
                raise agent.LLMError(
                    "timeout", "Ollama 响应超时（模型可能正在首次加载，请稍后重试）"
                ) from None
            except httpx.HTTPError:
                raise agent.LLMError(
                    "ollama_network_error", "无法连接 Ollama，请确认本地服务已启动"
                ) from None
            latency_ms = int((time.perf_counter() - started) * 1000)
            if chat.status_code >= 400:
                raise agent.sanitize_error(
                    "ollama", RuntimeError("http"), status=chat.status_code
                )
    except agent.LLMError as exc:
        logger.info("ollama probe failed code=%s", exc.code)
        raise

    tool_hint = (
        "支持工具调用"
        if supports_tools
        else "不支持或未声明工具调用"
        if supports_tools is False
        else "工具调用能力未知"
    )
    return _Probe(
        ok=True,
        available=True,
        supports_tools=supports_tools,
        models=names[:20],
        latency_ms=latency_ms,
        message=f"Ollama 连接成功，{tool_hint}",
    )


async def _test_litellm(provider: Provider) -> _Probe:
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
        "model": provider.litellm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 4,
        "timeout": 15,
    }
    if key:
        kwargs["api_key"] = key
    if provider.base_url:
        # 兼容代理（CC Switch / 自建网关）对 anthropic 同样要覆盖 api_base，
        # 否则「测试连接」会打到官方端点而不是用户填写的地址。
        kwargs["api_base"] = provider.base_url
    supports_tools = _litellm_supports_tools(litellm, provider)
    started = time.perf_counter()
    try:
        await litellm.acompletion(**kwargs)
    except BaseException as exc:  # noqa: BLE001 - 统一脱敏
        status = getattr(exc, "status_code", None)
        raise agent.sanitize_error(provider.error_kind, exc, status=status) from None
    latency_ms = int((time.perf_counter() - started) * 1000)
    tool_hint = (
        "支持工具调用"
        if supports_tools
        else "模型信息未声明工具调用"
        if supports_tools is False
        else "工具调用能力未知"
    )
    return _Probe(
        ok=True,
        available=True,
        supports_tools=supports_tools,
        latency_ms=latency_ms,
        message=f"连接成功，{tool_hint}",
    )


def _litellm_supports_tools(litellm_module: Any, provider: Provider) -> bool | None:
    """LiteLLM 的模型能力表；未知模型返回 None，不假装探测过。"""
    try:
        params = litellm_module.get_supported_openai_params(model=provider.litellm_model)
    except Exception:  # noqa: BLE001 - 未知模型/离线表缺失都按未知处理
        try:
            params = litellm_module.get_supported_openai_params(model=provider.model)
        except Exception:  # noqa: BLE001
            return None
    if not isinstance(params, (list, tuple)):
        return None
    return "tools" in params


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


@router.get("/sessions", summary="会话列表（按更新时间倒序，可按标题/首条消息搜索）")
def list_sessions(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, Any]:
    member_id = _current_member_id(session)
    if q and q.strip():
        rows = assistant_repo.search_session_rows(
            session, member_id, q, limit=limit, offset=offset
        )
    else:
        rows = assistant_repo.list_session_rows(session, member_id, limit=limit, offset=offset)
    items = [
        assistant_repo.session_to_dict(
            row, message_count=assistant_repo.count_messages(session, row.id)
        )
        for row in rows
    ]
    return {"items": items, "query": q or ""}


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


@router.patch("/sessions/{session_id}", summary="重命名会话")
def rename_session(session_id: str, payload: SessionPatch, session: SessionDep) -> dict[str, Any]:
    member_id = _current_member_id(session)
    row = _require_session(session, session_id, member_id)
    try:
        assistant_repo.rename_session(session, row, payload.title)
    except ValueError as exc:
        raise InvalidInputError(str(exc), code="invalid_title") from exc
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
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> MessageListOut:
    member_id = _current_member_id(session)
    _require_session(session, session_id, member_id)
    total = assistant_repo.count_messages(session, session_id)
    # 多取一条判断是否还有更早/更新的消息，避免 UI 先请求 total。
    rows = assistant_repo.list_message_rows(
        session, session_id, limit=limit + 1, offset=offset, order=order
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        _message_payload(row, assistant_repo.list_tool_calls(session, row.id)) for row in rows
    ]
    return MessageListOut(
        items=items, total=total, limit=limit, offset=offset, hasMore=has_more
    )


@router.get(
    "/sessions/{session_id}/export",
    summary="导出会话为 Markdown（默认不含工具原始返回与参数）",
)
def export_session(
    session_id: str,
    session: SessionDep,
    includeToolArgs: Annotated[bool, Query()] = False,
) -> Response:
    member_id = _current_member_id(session)
    row = _require_session(session, session_id, member_id)
    messages = [
        _message_payload(message, assistant_repo.list_tool_calls(session, message.id))
        for message in assistant_repo.list_message_rows(session, session_id, limit=10_000)
    ]
    provider = get_provider_store().find(row.provider_id) if row.provider_id else None
    model = None
    for message in messages:
        if message.get("model"):
            model = message["model"]
            break
    markdown = session_export.render_markdown(
        title=row.title,
        session_id=row.id,
        provider_label=provider.label if provider else None,
        model=model or (provider.model if provider else None),
        style=row.style,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        messages=messages,
        generated_at=utc_now().isoformat(),
        include_tool_args=includeToolArgs,
    )
    filename = session_export.export_filename(utc_now())
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


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
# 取消
# --------------------------------------------------------------------------- #


@router.post("/messages/{message_id}/cancel", summary="取消正在生成的回答")
async def cancel_message(message_id: str, session: SessionDep) -> dict[str, Any]:
    """优先停止活跃轮次；若进程重启后残留 ``streaming`` 记录，则直接标为 cancelled。"""
    member_id = _current_member_id(session)
    row = assistant_repo.get_message_row(session, message_id)
    if row is None:
        raise not_found("assistant_message", message_id)
    parent = assistant_repo.get_session_row(session, row.session_id)
    if parent is None or parent.member_id != member_id:
        raise not_found("assistant_message", message_id)
    if row.role != assistant_repo.ROLE_ASSISTANT:
        raise InvalidInputError(
            "only assistant messages can be cancelled", code="invalid_message_role"
        )

    if get_turn_registry().cancel(message_id):
        return {"messageId": message_id, "cancelled": True, "status": "cancelling"}

    if row.status == assistant_repo.STATUS_STREAMING:
        assistant_repo.update_message(
            session, row, status=assistant_repo.STATUS_CANCELLED, commit=True
        )
        return {"messageId": message_id, "cancelled": True, "status": "cancelled"}
    return {
        "messageId": message_id,
        "cancelled": False,
        "status": row.status,
    }


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
    # 用户手动命名过的会话不被首条消息覆盖；只有默认标题才自动取首条消息。
    auto_title = payload.content.strip()[:24] if is_first_user_message else None
    if auto_title and session_row.title and session_row.title != "新会话":
        auto_title = None

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
        data={
            "style": style,
            "providerId": provider.id,
            "providerLabel": provider.label,
            "model": provider.model,
        },
    )
    assistant_repo.touch_session(
        session,
        session_row,
        title=auto_title,
        provider_id=provider.id,
        style=style,
        record_id=payload.recordId or session_row.record_id,
        has_notes=payload.includeNotes or None,
        commit=True,
    )
    assistant_id = assistant_row.id
    user_id = user_row.id
    cancel = get_turn_registry().register(assistant_id, session_id)

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
            cancel=cancel,
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
    cancel: asyncio.Event,
) -> AsyncIterator[str]:
    watcher = asyncio.create_task(_watch_disconnect(request, cancel))
    content_parts: list[str] = []
    final: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    cancelled = False
    transparency: dict[str, Any] | None = None

    # 先告诉前端服务端消息 ID：停止生成时用它调用取消 API，而不是只断开连接。
    yield agent.format_sse(
        "start",
        {
            "sessionId": session_id,
            "userMessageId": user_id,
            "assistantMessageId": assistant_id,
            "provider": {
                "id": provider.id,
                "kind": provider.kind,
                "label": provider.label,
                "model": provider.model,
            },
        },
    )

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
            failure = {
                "code": "timeout",
                "message": f"本轮对话超过 {int(agent.TURN_TIMEOUT_S)} 秒，已停止",
            }
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
        # 先注销活跃轮次：取消请求到达时若已结束，改为走「残留 streaming 修正」。
        get_turn_registry().unregister(assistant_id)
        watcher.cancel()
        tool_session.close()
        _finalize_message(
            assistant_id,
            content="".join(content_parts),
            final=final,
            failure=failure,
            cancelled=cancelled,
            transparency=transparency,
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
    transparency: dict[str, Any] | None = None,
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
                if final.get("usage") is not None:
                    data["usage"] = final.get("usage")
                if final.get("durationMs") is not None:
                    data["durationMs"] = final.get("durationMs")
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
                if transparency is not None:
                    data["transparency"] = transparency
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
                if transparency is not None:
                    data["transparency"] = transparency
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

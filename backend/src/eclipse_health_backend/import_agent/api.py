"""Agent 数据导入 API（docs/IMPORT_AGENT_API.md）。

前缀 ``/import-agent``；SSE 事件与工具循环在 ``agent.py``，校验/落库在 ``kinds.py`` /
``commit.py``，沙箱在 ``sandbox.py``。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import SessionDep
from ..db.repositories import ensure_default_member, get_member_row
from ..domain.common import utc_now
from ..domain.errors import InvalidInputError, not_found
from ..llm.agent import LLMError, format_sse
from ..llm.providers import Provider, ProviderError, get_provider_store
from . import audit, limits, store
from .agent import AgentCancelled, AgentTimeout, make_adapter, stream_import_agent
from .commit import commit_proposals, select_proposals
from .errors import ImportAgentError, RecordValidationError
from .kinds import normalize_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import-agent", tags=["import-agent"])

_RUNS: dict[str, asyncio.Event] = {}
_RUNS_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providerId: str | None = Field(default=None, max_length=64)
    instructions: str | None = Field(default=None, max_length=2000)


class CommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[Any] | None = None
    memberId: str | None = Field(default=None, max_length=64)
    timezone: str = Field(default="UTC", max_length=64)


# --------------------------------------------------------------------------- #
# 公共
# --------------------------------------------------------------------------- #


def _conflict(message: str, code: str) -> ImportAgentError:
    return ImportAgentError(message, code=code, status_code=409)


def _resolve_provider(provider_id: str | None) -> Provider:
    store_ = get_provider_store()
    if provider_id:
        try:
            provider = store_.get(provider_id)
        except ProviderError as exc:
            raise ImportAgentError(
                "provider not found", code="provider_not_found", status_code=404
            ) from exc
        if not provider.enabled:
            raise _conflict("provider is disabled", "provider_disabled")
        return provider

    candidates = [provider for provider in store_.list() if provider.enabled]
    if not candidates:
        raise _conflict(
            "no LLM provider is configured; add one in settings", "provider_not_configured"
        )
    # 本地优先：隐私更好，也不需要联网。
    candidates.sort(key=lambda item: 0 if item.kind in {"ollama", "mock"} else 1)
    return candidates[0]


def _resolve_key(provider: Provider) -> str | None:
    if not provider.needs_key:
        return None
    if not provider.key_ref:
        raise _conflict("provider API key is not configured", "missing_api_key")
    try:
        return get_provider_store().resolve_api_key(provider)
    except ProviderError as exc:
        raise _conflict("stored API key could not be decrypted", "key_unavailable") from exc


def _claim(session_id: str) -> asyncio.Event:
    with _RUNS_LOCK:
        if session_id in _RUNS:
            raise _conflict("a run is already in progress for this session", "run_in_progress")
        cancel = asyncio.Event()
        _RUNS[session_id] = cancel
        return cancel


def _release(session_id: str) -> None:
    with _RUNS_LOCK:
        _RUNS.pop(session_id, None)


def _set_error(meta: dict[str, Any], code: str, message: str) -> None:
    meta["status"] = "error"
    meta["lastError"] = {"code": code, "message": message}


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidInputError(
            "timezone must be an IANA name such as Asia/Shanghai or UTC",
            code="invalid_timezone",
        ) from exc
    return value


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #


@router.post("/sessions", status_code=201, summary="创建导入 Agent 会话并上传文件")
def create_session(
    files: Annotated[list[UploadFile] | None, File()] = None,
    files_bracket: Annotated[list[UploadFile] | None, File(alias="files[]")] = None,
    single_file: Annotated[UploadFile | None, File(alias="file")] = None,
    path: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    store.cleanup_expired()
    uploads: list[UploadFile] = []
    for group in (files or [], files_bracket or [], [single_file] if single_file else []):
        for upload in group:
            if upload is not None and upload.filename:
                uploads.append(upload)
    session_id = store.new_session_id()
    workspace = store.create_workspace(session_id)
    try:
        entries = store.stage_uploads(workspace, uploads, path)
        now = utc_now()
        meta = {
            "sessionId": session_id,
            "status": "created",
            "createdAt": now.isoformat(),
            "expiresAt": (now + timedelta(hours=limits.SESSION_TTL_HOURS)).isoformat(),
            "providerId": None,
            "files": entries,
            "proposalCount": 0,
            "summary": None,
            "toolCalls": 0,
            "lastError": None,
            "commit": None,
        }
        store.write_meta(workspace, meta)
    except BaseException:
        store.delete_session(session_id)
        raise
    audit.record(
        "session_created",
        session_id,
        {
            "files": len(entries),
            "bytes": sum(int(item.get("size") or 0) for item in entries),
            "kinds": [item.get("kind") for item in entries],
        },
    )
    return {**store.session_view(meta), "proposals": [], "proposalsTruncated": False}


@router.get("/sessions", summary="最近的导入 Agent 会话")
def list_sessions(limit: Annotated[int, Query(ge=1, le=limits.MAX_SESSION_LIST)] = 20) -> dict[str, Any]:
    items = [
        store.session_view(meta, include_files=False)
        for meta in store.list_sessions(limit)
    ]
    return {"items": items}


@router.get("/sessions/{session_id}", summary="读取导入 Agent 会话")
def get_session(session_id: str) -> dict[str, Any]:
    workspace, meta = store.load_session(session_id)
    proposals = store.load_proposals(workspace) if meta.get("status") != "committed" else []
    preview = proposals[:200]
    return {
        **store.session_view(meta),
        "proposals": preview,
        "proposalCount": int(meta.get("proposalCount") or len(proposals)),
        "proposalsTruncated": len(proposals) > len(preview),
    }


@router.get("/sessions/{session_id}/proposals", summary="分页读取候选记录")
def list_proposals(
    session_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    workspace, _meta = store.load_session(session_id)
    proposals = store.load_proposals(workspace)
    return {
        "items": proposals[offset : offset + limit],
        "total": len(proposals),
        "limit": limit,
        "offset": offset,
    }


@router.delete("/sessions/{session_id}", status_code=204, summary="放弃会话并删除文件")
def discard_session(session_id: str) -> Response:
    _workspace, meta = store.load_session(session_id)
    status = str(meta.get("status") or "")
    store.delete_session(session_id)
    audit.record("discarded", session_id, {"status": status, "proposalCount": meta.get("proposalCount")})
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# 运行（SSE）
# --------------------------------------------------------------------------- #


@router.post(
    "/sessions/{session_id}/run",
    summary="运行 Agent（SSE：status/token/tool_call/tool_result/preview/done/error）",
    response_class=StreamingResponse,
)
async def run_session(
    session_id: str,
    request: Request,
    payload: RunRequest | None = None,
) -> StreamingResponse:
    workspace, meta = store.load_session(session_id)
    if meta.get("status") == "committed":
        raise _conflict("session is already committed", "session_committed")
    provider = _resolve_provider(payload.providerId if payload else None)
    api_key = _resolve_key(provider)
    cancel = _claim(session_id)

    store.reset_work_dirs(workspace)
    meta["status"] = "running"
    meta["providerId"] = provider.id
    meta["lastError"] = None
    meta["proposalCount"] = 0
    meta["summary"] = None
    meta["toolCalls"] = 0
    store.write_meta(workspace, meta)
    audit.record(
        "run_started",
        session_id,
        {"provider": provider.kind, "model": provider.model, "files": len(meta.get("files") or [])},
    )

    try:
        adapter = make_adapter(provider, api_key)
    except Exception:
        _release(session_id)
        _set_error(meta, "adapter_failed", "provider adapter could not be created")
        store.write_meta(workspace, meta)
        audit.record("run_error", session_id, {"code": "adapter_failed"})
        raise

    return StreamingResponse(
        _sse_events(
            request=request,
            session_id=session_id,
            workspace=workspace,
            meta=meta,
            provider=provider,
            adapter=adapter,
            instructions=payload.instructions if payload else None,
            cancel=cancel,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_events(
    *,
    request: Request,
    session_id: str,
    workspace: Any,
    meta: dict[str, Any],
    provider: Provider,
    adapter: Any,
    instructions: str | None,
    cancel: asyncio.Event,
) -> AsyncIterator[str]:
    watcher = asyncio.create_task(_watch_disconnect(request, cancel))
    error: dict[str, Any] | None = None
    try:
        async for event in stream_import_agent(
            provider=provider,
            adapter=adapter,
            session_id=session_id,
            meta=meta,
            instructions=instructions,
            cancel=cancel,
        ):
            yield format_sse(event["event"], event["data"])
    except AgentTimeout:
        error = {
            "code": "agent_timeout",
            "message": f"Agent 超过 {int(limits.MAX_TURN_SECONDS)} 秒，已停止",
        }
        yield format_sse("error", error)
    except AgentCancelled:
        error = {"code": "cancelled", "message": "Agent 已取消"}
        yield format_sse("error", error)
    except LLMError as exc:
        error = {"code": exc.code, "message": exc.message}
        yield format_sse("error", error)
    except Exception:
        logger.exception("import-agent run failed session=%s", session_id)
        error = {"code": "internal_error", "message": "导入 Agent 执行失败，请稍后重试"}
        yield format_sse("error", error)
    finally:
        watcher.cancel()
        _release(session_id)
        if error is not None:
            _set_error(meta, str(error.get("code")), str(error.get("message")))
        else:
            meta["status"] = "ready"
            meta["lastError"] = None
        try:
            store.write_meta(workspace, meta)
        except Exception:  # noqa: BLE001
            logger.warning("import-agent meta update failed session=%s", session_id)
        if error is not None:
            audit.record(
                "run_error",
                session_id,
                {"code": error.get("code"), "toolCalls": meta.get("toolCalls")},
            )
        else:
            audit.record(
                "run_done",
                session_id,
                {
                    "provider": provider.kind,
                    "toolCalls": meta.get("toolCalls"),
                    "proposalCount": meta.get("proposalCount"),
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
    except Exception:  # noqa: BLE001 - 探测失败就停止探测
        return


# --------------------------------------------------------------------------- #
# 提交
# --------------------------------------------------------------------------- #


@router.post("/sessions/{session_id}/commit", summary="确认并写入候选记录")
def commit_session(
    session_id: str,
    session: SessionDep,
    payload: CommitRequest | None = None,
) -> dict[str, Any]:
    workspace, meta = store.load_session(session_id)
    request = payload or CommitRequest()
    if meta.get("status") == "committed" and isinstance(meta.get("commit"), dict):
        return {
            "sessionId": session_id,
            "duplicateCommit": True,
            **meta["commit"],
        }
    if meta.get("status") == "running":
        raise _conflict("session is still running", "run_in_progress")

    proposals = store.load_proposals(workspace)
    if not proposals:
        raise ImportAgentError(
            "this session has no proposed records", code="no_proposals", status_code=422
        )
    try:
        selected = select_proposals(proposals, request.records)
    except RecordValidationError as exc:
        raise InvalidInputError(exc.message, code=exc.code, details=exc.details) from exc

    if request.memberId:
        if get_member_row(session, request.memberId) is None:
            raise not_found("member", request.memberId)
        member_id = request.memberId
    else:
        member_id = ensure_default_member(session).id
    timezone = _timezone(request.timezone)

    result = commit_proposals(
        session,
        workspace=workspace,
        meta=meta,
        proposals=selected,
        member_id=member_id,
        timezone=timezone,
    )
    meta["commit"] = result
    meta["status"] = "committed"
    store.write_meta(workspace, meta)
    store.delete_payload_dirs(workspace)
    audit.record(
        "committed",
        session_id,
        {
            "selected": len(selected),
            "created": result["created"],
            "skipped": result["skipped"],
            "failed": result["failed"],
            "counts": result.get("counts"),
        },
    )
    return {"sessionId": session_id, "duplicateCommit": False, **result}


# --------------------------------------------------------------------------- #
# 校验单条候选（供前端预览时复用；不是必须）
# --------------------------------------------------------------------------- #


def validate_record(raw: dict[str, Any], files: set[str]) -> dict[str, Any]:
    return normalize_record(raw, files=files)


__all__ = ["router"]

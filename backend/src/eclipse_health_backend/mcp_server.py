"""MCP stdio server（F3）：把本地对外 REST 暴露成只读工具。

入口：``python -m eclipse_health_backend.mcp_server``。

环境变量：

- ``EH_EXTERNAL_KEY``：必填，应用设置里创建的 API Key（scope 至少 read；
  ``ask_assistant`` 还需要 assistant）；
- ``EH_API_BASE``：默认 ``http://127.0.0.1:8765/api/v1``。

本模块只做 HTTP 客户端，不直接读数据库；权限、审计与脱敏都在后端 API 完成。
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__

DEFAULT_API_BASE = "http://127.0.0.1:8765/api/v1"
REQUEST_TIMEOUT_S = 30.0
ASK_TIMEOUT_S = 120.0


class ExternalApiError(RuntimeError):
    """后端不可达或返回业务错误；消息可直接展示给模型。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _api_base() -> str:
    return (os.environ.get("EH_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def _headers() -> dict[str, str]:
    key = (os.environ.get("EH_EXTERNAL_KEY") or "").strip()
    if not key:
        raise ExternalApiError(
            "EH_EXTERNAL_KEY is not set; create a key in eclipse health settings and "
            "pass it to the MCP server"
        )
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


async def _request_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    """所有工具共用的 HTTP 入口；测试可直接 monkeypatch 本函数。"""
    url = f"{_api_base()}{path}"
    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method, url, headers=headers, params=params, json=json_body
            )
    except httpx.HTTPError as exc:
        raise ExternalApiError(
            f"cannot reach eclipse health backend at {_api_base()} ({type(exc).__name__})"
        ) from exc

    if response.status_code == 401:
        raise ExternalApiError(
            "invalid API key: EH_EXTERNAL_KEY is unknown or revoked", status_code=401
        )
    if response.status_code == 403:
        raise ExternalApiError(
            "API key lacks the required scope (check the key's permissions)", status_code=403
        )
    if response.status_code >= 400:
        code = "http_error"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                code = str(payload.get("code") or code)
        except ValueError:
            payload = None
        raise ExternalApiError(
            f"backend returned HTTP {response.status_code} ({code})",
            status_code=response.status_code,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ExternalApiError("backend returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ExternalApiError("backend returned an unexpected payload")
    return data


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


server = MCPServer(
    name="eclipse-health",
    title="eclipse health",
    version=__version__,
    instructions=(
        "Local, read-only access to eclipse health records and ECG analyses. "
        "Use ask_assistant for natural-language interpretation; it requires an "
        "API key with the assistant scope and a configured LLM provider."
    ),
)


@server.tool(
    description="List recent health/ECG record summaries. No waveforms, notes or member names."
)
async def list_records(limit: int = 10, offset: int = 0) -> str:
    """List recent record summaries (1-200 per page)."""
    try:
        data = await _request_json(
            "GET", "/external/records", params={"limit": limit, "offset": offset}
        )
    except ExternalApiError as exc:
        raise ToolError(str(exc)) from exc
    return _json(data)


@server.tool(description="Get one record summary by ID; health data includes value/unit.")
async def get_record(record_id: str) -> str:
    """Get one record summary by its record ID."""
    try:
        data = await _request_json("GET", f"/external/records/{record_id}")
    except ExternalApiError as exc:
        raise ToolError(str(exc)) from exc
    return _json(data)


@server.tool(description="Get an analysis summary and measurements by analysis ID.")
async def get_analysis(analysis_id: str) -> str:
    """Get one analysis summary plus measurements (no beat-by-beat data)."""
    try:
        data = await _request_json("GET", f"/external/analyses/{analysis_id}")
    except ExternalApiError as exc:
        raise ToolError(str(exc)) from exc
    return _json(data)


@server.tool(description="Aggregate record and health metrics for the last N days (1-365).")
async def health_summary(days: int = 7) -> str:
    """Return record counts, heart rate/HRV/quality and health data aggregates."""
    try:
        data = await _request_json(
            "GET", "/external/summary", params={"days": days}
        )
    except ExternalApiError as exc:
        raise ToolError(str(exc)) from exc
    return _json(data)


@server.tool(
    description=(
        "Ask the in-app assistant a question about local data. Requires an API key "
        "with the assistant scope and a configured LLM provider."
    )
)
async def ask_assistant(question: str) -> str:
    """Ask the local assistant; returns the final answer and citations."""
    try:
        data = await _request_json(
            "POST",
            "/external/openai/v1/chat/completions",
            json_body={
                "model": "eclipse-health",
                "messages": [{"role": "user", "content": question}],
                "stream": False,
            },
            timeout=ASK_TIMEOUT_S,
        )
    except ExternalApiError as exc:
        raise ToolError(str(exc)) from exc
    choices = data.get("choices")
    content = ""
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    if not content:
        raise ToolError("assistant returned no content")
    return _json({"content": content, "citations": data.get("citations") or []})


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()


__all__ = ["ExternalApiError", "main", "server"]

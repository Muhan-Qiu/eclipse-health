"""模块工具注册（B2）：llm 授权过滤、命名空间、执行裁剪与错误映射。

测试用 ``fixtures/modules/tools`` 这个只读 ai-tool 模块；每个用例装一份临时包，
不依赖仓库里任何真实第三方代码。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.llm import agent
from eclipse_health_backend.llm.providers import Provider
from eclipse_health_backend.llm.tools import (
    MAX_TOOL_RESULT_JSON,
    TOOL_NAMES,
    ToolBox,
    module_tool_alias,
)
from eclipse_health_backend.modules.manager import ModuleManager
from eclipse_health_backend.modules.package import pack_directory, write_checksums

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "modules" / "tools"
MODULE_ID = "io.github.example.ai-toolbox"


def _build_package(tmp_path: Path) -> Path:
    token = uuid.uuid4().hex[:8]
    source = tmp_path / f"toolbox-src-{token}"
    shutil.copytree(FIXTURE_DIR, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    write_checksums(source)
    output = tmp_path / f"toolbox-{token}.ehmod"
    pack_directory(source, output)
    return output


@pytest.fixture()
def tool_manager(tmp_path: Path, client: TestClient) -> Iterator[ModuleManager]:
    manager = ModuleManager(data_dir=tmp_path / "modules-data", call_timeout_s=0.6)
    package = _build_package(tmp_path)
    manager.install(package, enable=True)
    try:
        yield manager
    finally:
        with contextlib.suppress(Exception):
            manager.uninstall(MODULE_ID)
        manager.shutdown()


def _specs(manager: ModuleManager) -> list[dict[str, Any]]:
    with session_scope() as session:
        return ToolBox(session, "mem_test", manager=manager).tool_specs()


def _call(manager: ModuleManager, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    with session_scope() as session:
        return ToolBox(session, "mem_test", manager=manager).execute(name, args or {})


def _alias(tool_id: str) -> str:
    return module_tool_alias(MODULE_ID, tool_id)


def test_tools_hidden_without_llm_permission(tool_manager: ModuleManager) -> None:
    tool_manager.revoke_permission(MODULE_ID, "llm")

    names = [spec["function"]["name"] for spec in _specs(tool_manager)]
    assert names == list(TOOL_NAMES)
    assert not any(name.startswith("m_") for name in names)

    outcome = _call(tool_manager, _alias("echo.text"), {"text": "hi"})
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "UNKNOWN_TOOL"


def test_tools_registered_after_grant(tool_manager: ModuleManager) -> None:
    specs = _specs(tool_manager)
    names = [spec["function"]["name"] for spec in specs]
    assert names[: len(TOOL_NAMES)] == list(TOOL_NAMES)
    assert _alias("echo.text") in names

    alias = _alias("echo.text")
    assert alias.startswith("m_")
    assert len(alias) <= 64
    assert "." not in alias.split("_", 2)[2]

    echo = next(spec for spec in specs if spec["function"]["name"] == alias)
    parameters = echo["function"]["parameters"]
    assert parameters["type"] == "object"
    assert parameters["additionalProperties"] is False
    assert "text" in parameters["properties"]
    assert "AI Toolbox" in echo["function"]["description"]

    leak = next(spec for spec in specs if spec["function"]["name"] == _alias("data.leak"))
    assert leak["function"]["parameters"]["additionalProperties"] is False


def test_execute_returns_trimmed_result(tool_manager: ModuleManager) -> None:
    outcome = _call(tool_manager, _alias("echo.text"), {"text": "hello"})
    assert outcome["ok"] is True
    assert outcome["result"] == {"text": "hello", "length": 5}
    assert outcome["citations"] == []
    assert "AI Toolbox (test fixture) · Echo text" in outcome["summary"]

    leaky = _call(tool_manager, _alias("data.leak"), {"size": 4000, "rows": 20})
    assert leaky["ok"] is True
    text = json.dumps(leaky["result"], ensure_ascii=False)
    for forbidden in ("samples", "waveform", "notes", "memberName", "beats", "Alice Example"):
        assert forbidden not in text
    assert leaky["result"]["truncated"] is True
    assert len(text) <= MAX_TOOL_RESULT_JSON

    small = _call(tool_manager, _alias("data.leak"), {"size": 5000, "rows": 1})
    assert small["result"]["measurements"][0]["code"] == "heart_rate_mean"
    assert "truncated" not in small["result"]
    # 单个字符串超过 2000 字符会被截短，避免一条字段撑爆上下文。
    assert len(small["result"]["rows"][0]) == 2000


def test_module_error_is_mapped_without_internal_text(tool_manager: ModuleManager) -> None:
    outcome = _call(tool_manager, _alias("demo.fail"))
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "TOOL_FAILED"
    assert "boom" not in json.dumps(outcome, ensure_ascii=False)
    assert "AI Toolbox (test fixture) · Failing tool" in outcome["summary"]


def test_module_timeout_is_mapped(tool_manager: ModuleManager) -> None:
    outcome = _call(tool_manager, _alias("demo.slow"))
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "TOOL_FAILED"


def test_unknown_module_tool(tool_manager: ModuleManager) -> None:
    outcome = _call(tool_manager, "m_deadbeef_nope")
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "UNKNOWN_TOOL"


def test_builtin_tools_unaffected(tool_manager: ModuleManager, default_member: dict) -> None:
    outcome = _call(tool_manager, "list_records", {"limit": 5})
    assert outcome["ok"] is True
    assert outcome["result"]["count"] == 0
    assert _call(tool_manager, "drop_table")["result"]["error"]["code"] == "UNKNOWN_TOOL"


class _CaptureAdapter(agent.ChatAdapter):
    """只记录工具表，直接给出回答；用来验证 agent 用了动态工具来源。"""

    def __init__(self) -> None:
        self.tools: list[dict[str, Any]] | None = None

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        cancel: asyncio.Event,
    ) -> Any:
        self.tools = tools
        yield {"type": "token", "text": "ok"}


def test_agent_uses_dynamic_tool_table(tool_manager: ModuleManager) -> None:
    adapter = _CaptureAdapter()
    provider = Provider(id="llm_test", kind="mock", label="Test", model="mock-1")

    async def runner() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with session_scope() as session:
            toolbox = ToolBox(session, "mem_test", manager=tool_manager)
            async for event in agent.stream_reply(
                provider=provider,
                adapter=adapter,
                messages=[{"role": "user", "content": "hi"}],
                toolbox=toolbox,
                transparency={},
                cancel=asyncio.Event(),
            ):
                events.append(event)
        return events

    events = asyncio.run(runner())
    assert events[-1]["event"] == "done"
    assert adapter.tools is not None
    names = [spec["function"]["name"] for spec in adapter.tools]
    assert next(iter(TOOL_NAMES)) in names
    assert _alias("echo.text") in names

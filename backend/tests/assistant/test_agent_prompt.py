"""V4.1：助手提示词优先给建议，免责声明只出现一次且不强制每轮重复。"""

from __future__ import annotations

from eclipse_health_backend.llm import agent


def test_chat_prompt_prioritizes_actionable_answer() -> None:
    prompt = agent.SYSTEM_PROMPT
    assert "先给结论和可执行建议" in prompt
    assert "不要用免责声明或「我不知道」代替回答" in prompt
    assert "回答末尾用一句话提醒" not in prompt
    # 免责说明仍保留一次，由界面统一展示。
    assert "不构成医学诊断" in prompt


def test_coach_prompt_prioritizes_actionable_answer() -> None:
    prompt = agent.COACH_SYSTEM_PROMPT
    assert "先给建议" in prompt
    assert "不要用免责声明或「数据不足」开头" in prompt
    assert "回答末尾用一句话提醒" not in prompt
    assert "不构成医学诊断" in prompt
    for token in ("胸痛", "晕厥", "呼吸困难"):
        assert token in prompt


def test_mock_answer_does_not_append_disclaimer() -> None:
    latest = {"id": "analysis_1", "status": "completed", "summary": "ok"}
    messages = [
        {
            "role": "tool",
            "name": "get_measurements",
            "content": (
                '{"items": [{"code": "heart_rate_mean", "value": 72, "unit": "bpm"}]}'
            ),
        }
    ]
    answer = agent._mock_answer(messages, latest)
    assert "平均心率 72" in answer
    assert "不构成医学诊断" not in answer


def _build(selected_modules=None) -> str:
    messages = agent.build_messages(
        context_text="{}",
        history=[],
        content="你好",
        style="brief",
        selected_modules=selected_modules,
    )
    return messages[0]["content"]


def test_build_messages_appends_selected_modules() -> None:
    selected = [
        {
            "id": "io.example.ecg",
            "name": "ECG 助手",
            "description": "解释心电数据",
            "type": "ai-tool",
            "tools": [{"id": "echo.text", "name": "回显", "description": "回显文本"}],
            "pages": [{"id": "overview", "title": "总览页"}],
        }
    ]
    system = _build(selected)
    assert "本轮用户选择的模块" in system
    assert "ECG 助手" in system
    assert "io.example.ecg" in system
    assert "echo.text" in system
    assert "总览页" in system
    assert "优先调用" in system
    assert "其他已安装模块的工具仍可用" in system


def test_build_messages_without_selected_modules_has_no_block() -> None:
    system = _build()
    assert "本轮用户选择的模块" not in system


def test_build_messages_notes_module_without_tools() -> None:
    selected = [
        {
            "id": "io.example.empty",
            "name": "空模块",
            "description": "",
            "type": "page",
            "tools": [],
            "pages": [],
        }
    ]
    system = _build(selected)
    assert "该模块没有向 Agent 暴露工具，可在模块工作台使用" in system


def test_selected_module_description_is_truncated() -> None:
    selected = [
        {
            "id": "io.example.long",
            "name": "长模块",
            "description": "x" * 400,
            "type": "ai-tool",
            "tools": [],
            "pages": [],
        }
    ]
    system = _build(selected)
    assert "x" * 300 in system
    assert "x" * 301 not in system

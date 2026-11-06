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

"""coach 模式系统提示：关键段落、记忆开关、非 coach 不变。"""

from __future__ import annotations

from typing import Any

from eclipse_health_backend.coach.context import render_coach_context
from eclipse_health_backend.llm import agent


def _coach_context() -> dict[str, Any]:
    return {
        "scores": {
            "overall": 78,
            "grade": "good",
            "categories": [
                {"label": "心脏", "score": 82, "grade": "good", "factors": ["静息心率 62 bpm"]}
            ],
            "missing": ["睡眠"],
        },
        "health": {
            "steps": {"dailyAverage": 6500, "days": 5, "latest": 7000},
            "heartRate": {"average": 70, "min": 55, "max": 98, "samples": 10},
            "sleep": {"averageHours": 7.2, "days": 5, "latestHours": 7.5},
            "weight": {"value": 62.4, "unit": "kg"},
            "bloodPressure": {"systolic": 118, "diastolic": 76, "unit": "mmHg"},
        },
        "exercises": [
            {
                "activity": "walk",
                "durationSec": 1800,
                "distanceKm": 3.2,
                "intensity": "moderate",
                "startAt": "2026-10-30T08:00:00+08:00",
            }
        ],
        "memory": {"content": "喜欢晨跑，晚上十点后不吃东西"},
        "weather": {
            "city": "上海",
            "days": [
                {
                    "date": "2026-10-31",
                    "tempMin": 14,
                    "tempMax": 22,
                    "precipitationProbability": 10,
                    "weatherCode": 1,
                }
            ],
        },
    }


def _messages(**kwargs: Any) -> list[dict[str, Any]]:
    return agent.build_messages(
        context_text='{"recentRecords": []}',
        history=[],
        content="我最近睡不好，怎么办？",
        style="brief",
        **kwargs,
    )


def test_coach_prompt_contains_sections_and_red_flags() -> None:
    messages = _messages(mode="coach", coach_context=_coach_context())
    system = messages[0]["content"]
    for token in ("健康教练", "评分", "健康数据", "运动记录", "记忆", "天气"):
        assert token in system
    for token in ("胸痛", "晕厥", "呼吸困难", "不构成医学诊断"):
        assert token in system
    assert "喜欢晨跑" in system
    assert "渐进" in system
    assert messages[-1] == {"role": "user", "content": "我最近睡不好，怎么办？"}


def test_memory_is_not_injected_when_absent() -> None:
    context = _coach_context()
    context["memory"] = None
    system = _messages(mode="coach", coach_context=context)[0]["content"]
    assert "喜欢晨跑" not in system
    assert "【个人记忆" not in system


def test_empty_coach_context_renders_placeholder() -> None:
    assert render_coach_context(None) == "（暂无教练上下文数据）"
    assert render_coach_context({}) == "（暂无教练上下文数据）"
    system = _messages(mode="coach")[0]["content"]
    assert "健康教练" in system
    assert "（暂无教练上下文数据）" in system


def test_non_coach_mode_is_unchanged() -> None:
    baseline = _messages()
    explicit_chat = _messages(mode="chat", coach_context=_coach_context())
    unknown_mode = _messages(mode="doctor", coach_context=_coach_context())
    assert baseline == explicit_chat == unknown_mode
    system = baseline[0]["content"]
    assert system.startswith(agent.SYSTEM_PROMPT)
    assert "健康教练" not in system
    assert "喜欢晨跑" not in system

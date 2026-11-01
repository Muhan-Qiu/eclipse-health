"""会话导出为 Markdown（B4-08）。

默认脱敏，刻意只导出「对话正文 + 工具名称/结果摘要 + 引用 ID」：

- 不导出工具原始返回（B3-04 也不落库）；
- 不导出工具参数（``include_tool_args=True`` 才带，供用户自查）；
- 波形、逐搏数据、备注、成员姓名本来就不在会话表里。

导出是用户主动动作，内容仍是用户自己的数据，因此不做二次打码，只在文首声明范围。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

STATUS_LABELS = {
    "completed": "完成",
    "cancelled": "已停止",
    "error": "失败",
    "streaming": "生成中",
}


def render_markdown(
    *,
    title: str,
    session_id: str,
    provider_label: str | None,
    model: str | None,
    style: str | None,
    created_at: str,
    updated_at: str,
    messages: list[dict[str, Any]],
    generated_at: str,
    include_tool_args: bool = False,
) -> str:
    lines: list[str] = [
        f"# {title or '会话'}",
        "",
        f"- 会话 ID：`{session_id}`",
        f"- 导出时间：{generated_at}",
        f"- 创建时间：{created_at}",
        f"- 最后更新：{updated_at}",
        f"- 提供商 / 模型：{provider_label or '—'} / {model or '—'}",
        f"- 回答风格：{style or '—'}",
        f"- 消息数：{len(messages)}",
        "",
        (
            "> 本导出由 eclipse health 生成，仅包含对话正文、工具名称与结果摘要、引用 ID；"
            "不含波形、逐搏数据、成员姓名、备注与工具原始返回。"
        ),
        "",
    ]

    for message in messages:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role == "user":
            lines += ["## 用户", "", content or "（空）", ""]
            continue

        lines += ["## 助手", "", content or "（空）", ""]
        status = message.get("status")
        if status and status != "completed":
            lines.append(f"> 状态：{STATUS_LABELS.get(status, status)}")
            error = message.get("error") or {}
            if isinstance(error, dict) and error.get("message"):
                lines.append(f"> 错误：{error.get('message')}")

        calls = message.get("toolCalls") or []
        if calls:
            lines += ["", "**工具调用**", ""]
            for call in calls:
                if not isinstance(call, dict):
                    continue
                failed = "" if call.get("ok", True) else "（失败）"
                duration = int(call.get("durationMs") or 0)
                summary = str(call.get("resultSummary") or "—")
                lines.append(
                    f"- `{call.get('name') or 'unknown'}`{failed} · {duration} ms · {summary}"
                )
                if include_tool_args:
                    args = json.dumps(
                        call.get("args") or {}, ensure_ascii=False, sort_keys=True
                    )
                    lines.append(f"  - 参数：`{args}`")

        citations = message.get("citations") or []
        labels = [
            f"{item.get('kind')}:{item.get('id')}"
            for item in citations
            if isinstance(item, dict) and item.get("id")
        ]
        if labels:
            lines += ["", f"引用：{', '.join(labels)}"]

        meta: list[str] = []
        usage = message.get("usage") or {}
        if isinstance(usage, dict) and (
            usage.get("promptTokens") is not None
            or usage.get("completionTokens") is not None
        ):
            meta.append(
                f"tokens {usage.get('promptTokens')}/{usage.get('completionTokens')}"
                f"（{usage.get('source') or 'provider'}）"
            )
        if message.get("durationMs") is not None:
            meta.append(f"{int(message['durationMs'])} ms")
        if message.get("model"):
            meta.append(str(message["model"]))
        if meta:
            lines += ["", f"> {' · '.join(meta)}"]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export_filename(now: datetime) -> str:
    """ASCII 文件名，避免 Content-Disposition 编码问题。"""
    return f"eclipse-health-assistant-{now:%Y%m%d-%H%M%S}.md"


__all__ = ["STATUS_LABELS", "export_filename", "render_markdown"]

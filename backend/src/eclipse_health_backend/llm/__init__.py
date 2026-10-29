"""LLM 助手：provider 配置、只读工具、对话循环。

模块边界：

- ``providers`` 只管配置与凭据（DPAPI），不做网络请求；
- ``tools`` 只暴露最小切片（summary / measurement / quality），绝不带波形与备注；
- ``agent`` 负责一次对话的工具循环与 SSE 事件，不碰 HTTP 层细节。
"""

from __future__ import annotations

__all__ = ["agent", "providers", "tools"]

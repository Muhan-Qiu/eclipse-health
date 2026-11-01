"""A5 · Agent 数据导入（受限沙箱 + 候选记录）。

对外只暴露 FastAPI router；解析、沙箱、校验、落库分在独立模块里，方便单测。
"""

from __future__ import annotations

__all__ = ["router"]


def __getattr__(name: str):  # 避免导入包时就拉起 FastAPI 路由与 DB 依赖
    if name == "router":
        from .api import router

        return router
    raise AttributeError(name)

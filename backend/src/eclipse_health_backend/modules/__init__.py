"""eclipse health 模块系统内核（B1）。

对外入口：
- `router`：挂到 /api/v1/modules（B1-01 负责前缀）
- `init_module_system()`：启动时可选调用
- `ModuleManager`：测试/内部直接使用
"""

from __future__ import annotations

from .api import get_manager, init_module_system, router, shutdown_module_system
from .errors import ModuleError
from .manager import ModuleManager

__all__ = [
    "ModuleError",
    "ModuleManager",
    "get_manager",
    "init_module_system",
    "router",
    "shutdown_module_system",
]

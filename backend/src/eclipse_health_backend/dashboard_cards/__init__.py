"""自定义仪表盘卡片（A8）。

卡片只做「声明式查询」：kind + aggregation + windowDays + view，
不执行任意代码，也不绕开 ``records`` 直接读文件。
"""

from __future__ import annotations

from . import api, catalog, models, service

__all__ = ["api", "catalog", "models", "service"]

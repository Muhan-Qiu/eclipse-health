"""应用内模块市场后端：签名索引、下载校验、安装与更新检查。"""

from __future__ import annotations

from .errors import MarketplaceError
from .index import fetch_index, reset_cache, verify_and_validate
from .models import MarketplaceEntry, MarketplaceIndex
from .service import MarketplaceService

__all__ = [
    "MarketplaceEntry",
    "MarketplaceError",
    "MarketplaceIndex",
    "MarketplaceService",
    "fetch_index",
    "reset_cache",
    "verify_and_validate",
]

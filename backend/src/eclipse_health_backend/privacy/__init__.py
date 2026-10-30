"""隐私中心：存储用量、清空全部数据、桌面设置持久化。"""

from __future__ import annotations

from .service import purge_all, storage_info
from .settings_store import load_settings, save_settings

__all__ = ["load_settings", "purge_all", "save_settings", "storage_info"]

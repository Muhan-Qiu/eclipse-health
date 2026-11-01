"""桌面设置持久化（H1/H2）。

设置独立于数据库存放在 ``data/settings.json``，清空数据时保留。
``telemetryEnabled`` 固定为 ``False``：项目没有遥测实现，读取时永远回填 false。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..settings import get_settings
from ..storage.files import atomic_write_bytes

DEFAULT_SETTINGS: dict[str, Any] = {
    "closeToTray": True,
    "splashEnabled": True,
    "telemetryEnabled": False,
    "locale": None,
}

SUPPORTED_LOCALES = ("zh-CN", "en-US")
MUTABLE_KEYS = ("closeToTray", "splashEnabled", "locale")


def settings_path() -> Path:
    return get_settings().data_dir / "settings.json"


def _normalize(raw: Any) -> dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return result
    for key in ("closeToTray", "splashEnabled"):
        if isinstance(raw.get(key), bool):
            result[key] = raw[key]
    locale = raw.get("locale")
    if locale in SUPPORTED_LOCALES:
        result["locale"] = locale
    # 无论文件里写了什么，遥测都不存在。
    result["telemetryEnabled"] = False
    return result


def load_settings() -> dict[str, Any]:
    path = settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)
    return _normalize(raw)


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    for key in MUTABLE_KEYS:
        if key not in patch:
            continue
        value = patch[key]
        if key == "locale":
            if value is None or value in SUPPORTED_LOCALES:
                current[key] = value
            continue
        if isinstance(value, bool):
            current[key] = value
    current["telemetryEnabled"] = False
    payload = json.dumps(current, ensure_ascii=False, indent=2) + "\n"
    atomic_write_bytes(settings_path(), payload.encode("utf-8"))
    return current


__all__ = [
    "DEFAULT_SETTINGS",
    "MUTABLE_KEYS",
    "SUPPORTED_LOCALES",
    "load_settings",
    "save_settings",
    "settings_path",
]

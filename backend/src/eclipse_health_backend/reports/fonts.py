"""中文字体：优先微软雅黑，回退黑体/宋体/Noto。

matplotlib 的默认字体不含中文字形，直接用会输出方块。这里在渲染前显式注册
可用字体；一个都找不到时抛 ``FontUnavailableError``，绝不静默输出方块。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)

from matplotlib import font_manager
from matplotlib.font_manager import FontProperties

from .errors import FontUnavailableError

FONT_CANDIDATES = (
    "msyh.ttc",  # 微软雅黑
    "msyh.ttf",
    "msyhbd.ttc",
    "simhei.ttf",  # 黑体
    "simsun.ttc",  # 宋体
    "NotoSansCJK-Regular.ttc",
    "NotoSansSC-Regular.otf",
    "SourceHanSansSC-Regular.otf",
    "wqy-microhei.ttc",
)

_configure_lock = threading.Lock()
_configured: tuple[str, Path] | None = None


def _font_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get("EH_REPORT_FONT")
    if override:
        path = Path(override)
        if path.is_file():
            roots.append(path)
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    roots.append(Path(windir) / "Fonts")
    roots.append(Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts")
    roots.append(Path("/usr/share/fonts"))
    roots.append(Path("/System/Library/Fonts"))
    return roots


def find_cjk_font() -> Path | None:
    """按候选顺序找第一个存在的字体文件；``EH_REPORT_FONT`` 可显式指定。"""
    override = os.environ.get("EH_REPORT_FONT")
    if override:
        path = Path(override)
        if path.is_file():
            return path
    for root in _font_roots():
        for name in FONT_CANDIDATES:
            candidate = root / name
            if candidate.is_file():
                return candidate
        if root.is_dir():
            # 最后兜底：任意含 CJK 字样的字体文件
            for candidate in root.glob("*CJK*"):
                if candidate.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                    return candidate
    return None


def require_cjk_font() -> Path:
    path = find_cjk_font()
    if path is None:
        raise FontUnavailableError("未找到可用的中文字体，无法生成中文报告")
    return path


def configure_fonts() -> tuple[str, Path]:
    """注册中文字体并设置 matplotlib 全局参数；线程安全、幂等。"""
    global _configured
    with _configure_lock:
        if _configured is not None:
            return _configured
        path = require_cjk_font()
        font_manager.fontManager.addfont(str(path))
        name = FontProperties(fname=str(path)).get_name()
        matplotlib.rcParams.update(
            {
                "font.family": [name],
                "axes.unicode_minus": False,
                "pdf.fonttype": 42,
                "ps.fonttype": 42,
            }
        )
        _configured = (name, path)
        return _configured


def font_supports_cjk(path: Path, char: str = "心") -> bool:
    """字体是否真的含有中文形（防止选到拉丁-only 的回退文件）。"""
    try:
        from matplotlib.ft2font import FT2Font

        return FT2Font(str(path)).get_char_index(ord(char)) != 0
    except Exception:  # noqa: BLE001 - 字体损坏时按不支持处理
        return False


__all__ = [
    "FONT_CANDIDATES",
    "configure_fonts",
    "find_cjk_font",
    "font_supports_cjk",
    "require_cjk_font",
]

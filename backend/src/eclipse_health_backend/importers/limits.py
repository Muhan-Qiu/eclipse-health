"""导入链路的硬限制。

测试通过 monkeypatch 这里的常量来构造「超大文件 / ZIP 炸弹」场景，
所以调用方必须写成 ``limits.MAX_UPLOAD_BYTES``，不要在导入时复制成局部名。
"""

from __future__ import annotations

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
ZIP_MAX_FILES = 200
ZIP_MAX_TOTAL_BYTES = 300 * 1024 * 1024
IMPORT_TTL_HOURS = 24

__all__ = [
    "IMPORT_TTL_HOURS",
    "MAX_UPLOAD_BYTES",
    "ZIP_MAX_FILES",
    "ZIP_MAX_TOTAL_BYTES",
]

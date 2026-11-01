"""导入链路的硬限制。

测试通过 monkeypatch 这里的常量来构造「超大文件 / ZIP 炸弹」场景，
所以调用方必须写成 ``limits.MAX_UPLOAD_BYTES``，不要在导入时复制成局部名。
"""

from __future__ import annotations

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
ZIP_MAX_FILES = 200
ZIP_MAX_TOTAL_BYTES = 300 * 1024 * 1024
IMPORT_TTL_HOURS = 24

# 健康数据导出（Apple / 小米）一次最多导入的记录数；超过时报错而不是 OOM。
HEALTH_MAX_RECORDS = 20_000
HEALTH_MAX_ECG_FILES = 200
# 超过这个数量在预览里提示「数据较多，提交需要更久」。
HEALTH_LARGE_RECORDS = 2_000

__all__ = [
    "HEALTH_LARGE_RECORDS",
    "HEALTH_MAX_ECG_FILES",
    "HEALTH_MAX_RECORDS",
    "IMPORT_TTL_HOURS",
    "MAX_UPLOAD_BYTES",
    "ZIP_MAX_FILES",
    "ZIP_MAX_TOTAL_BYTES",
]

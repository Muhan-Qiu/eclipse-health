"""导入链路的硬限制。

测试通过 monkeypatch 这里的常量来构造「超大文件 / ZIP 炸弹」场景，
所以调用方必须写成 ``limits.MAX_UPLOAD_BYTES``，不要在导入时复制成局部名。
"""

from __future__ import annotations

# 健康导出没有固定大小：Apple Health 的 export.xml、多年份 ECG 目录都可能很大。
# 这里只保留防止磁盘被误写的上限（16 GiB / 20 万文件），不再是 200 MB / 200 个。
MAX_UPLOAD_BYTES = 16 * 1024 * 1024 * 1024
ZIP_MAX_FILES = 200_000
ZIP_MAX_TOTAL_BYTES = 32 * 1024 * 1024 * 1024
IMPORT_TTL_HOURS = 24

# 健康数据导出一次最多导入的记录数；仅为避免浏览器/内存失控，不限制正常年份。
HEALTH_MAX_RECORDS = 5_000_000
HEALTH_MAX_ECG_FILES = 200_000
# 超过这个数量在预览里提示「数据较多，提交需要更久」。
HEALTH_LARGE_RECORDS = 50_000

__all__ = [
    "HEALTH_LARGE_RECORDS",
    "HEALTH_MAX_ECG_FILES",
    "HEALTH_MAX_RECORDS",
    "IMPORT_TTL_HOURS",
    "MAX_UPLOAD_BYTES",
    "ZIP_MAX_FILES",
    "ZIP_MAX_TOTAL_BYTES",
]

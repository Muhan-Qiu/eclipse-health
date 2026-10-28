"""两步导入链路：预览 → 校正 → 提交（B2-02）。

适配器只负责「文件 → ParsedImport」，入库与校验在 ``importers.api`` 完成。
"""

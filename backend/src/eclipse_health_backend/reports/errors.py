"""报告生成错误。

字体缺失等渲染前置条件失败时抛 ``ReportGenerationError``，由 API 统一映射为
``{code, message, details}``；不输出带方块字符的报告。
"""

from __future__ import annotations

from ..domain.errors import ApiError


class ReportGenerationError(ApiError):
    status_code = 500
    code = "report_generation_failed"


class FontUnavailableError(ReportGenerationError):
    code = "report_font_missing"

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            details={"hint": "安装微软雅黑/黑体/宋体，或设置 EH_REPORT_FONT 指向字体文件"},
        )


__all__ = ["FontUnavailableError", "ReportGenerationError"]

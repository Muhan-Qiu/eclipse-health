"""报告生成：内容组装、PDF 模板、PNG 分享卡、字体与持久化服务。

渲染只依赖 matplotlib + Pillow（均为本地已安装依赖），不联网、不调用浏览器。
重渲染模块按需在 ``service.create_report`` 内导入，避免后端启动就加载 matplotlib。
"""

from __future__ import annotations

from .content import (
    DISCLAIMER,
    WATERMARK,
    ReportContent,
    Waveform,
    build_report_content,
)
from .errors import FontUnavailableError, ReportGenerationError

__all__ = [
    "DISCLAIMER",
    "WATERMARK",
    "FontUnavailableError",
    "ReportContent",
    "ReportGenerationError",
    "Waveform",
    "build_report_content",
]

"""厂商格式占位：只为接口与注册表留位，不做任何猜测性解析。

真实解析需要样本与文档，计划 B3/B4 实现；在此之前显式返回 422 ``unsupported_format``。
"""

from __future__ import annotations

from .base import Detection, ImportAdapter, ImportSource, ParsedImport, ParseParameters, PreviewData
from .errors import unsupported_format


class PlaceholderAdapter(ImportAdapter):
    supported = False

    def __init__(self, adapter_id: str, fmt: str, label: str) -> None:
        self.adapter_id = adapter_id
        self.format = fmt
        self.label = label
        self.waiting_reason = f"{label} 格式等待真实样本与文档，计划 B3 实现"

    def detect(self, source: ImportSource) -> Detection | None:
        return None

    def preview(self, source: ImportSource) -> PreviewData:
        raise unsupported_format(
            self.waiting_reason,
            details={"adapterId": self.adapter_id, "supported": False},
        )

    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        raise unsupported_format(
            self.waiting_reason,
            details={"adapterId": self.adapter_id, "supported": False},
        )


def placeholder_adapters() -> list[PlaceholderAdapter]:
    return [
        PlaceholderAdapter("org.eclipsehealth.samsung", "samsung", "Samsung Health"),
        PlaceholderAdapter("org.eclipsehealth.huawei", "huawei", "华为运动健康"),
        PlaceholderAdapter("org.eclipsehealth.apple", "apple", "Apple Health"),
        PlaceholderAdapter("org.eclipsehealth.scp-ecg", "scp-ecg", "SCP-ECG"),
    ]


__all__ = ["PlaceholderAdapter", "placeholder_adapters"]

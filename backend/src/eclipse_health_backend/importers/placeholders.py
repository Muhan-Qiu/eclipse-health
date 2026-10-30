"""厂商格式占位。

EDF / SCP-ECG / Apple / Samsung / 华为已在 B4-03 接入真实适配器，
因此这里不再保留它们的占位。``PlaceholderAdapter`` 保留给后续格式
（例如 DICOM）：在拿到样本与文档前只返回「等待样本」的明确错误，
不做任何猜测性解析。
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
        self.waiting_reason = f"{label} 格式等待真实样本与文档"

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
    return []


__all__ = ["PlaceholderAdapter", "placeholder_adapters"]

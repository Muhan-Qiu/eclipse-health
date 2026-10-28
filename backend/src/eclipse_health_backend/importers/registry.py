"""格式注册与按置信度探测。

顺序：WFDB → CSV → 厂商占位。占位适配器不参与自动探测，
只在用户显式 ``hintFormat`` 时给出「等待样本」的明确错误。
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import Detection, ImportAdapter, ImportSource
from .errors import UnsupportedFormatError, unsupported_format

AUTO_HINTS = {"", "auto"}


class AdapterRegistry:
    def __init__(self, adapters: Iterable[ImportAdapter] = ()) -> None:
        self._adapters: list[ImportAdapter] = list(adapters)

    def register(self, adapter: ImportAdapter) -> None:
        self._adapters.append(adapter)

    def adapters(self) -> tuple[ImportAdapter, ...]:
        return tuple(self._adapters)

    def find(self, key: str) -> ImportAdapter | None:
        wanted = key.strip().lower()
        for adapter in self._adapters:
            if adapter.adapter_id.lower() == wanted or adapter.format.lower() == wanted:
                return adapter
        return None

    def detect(
        self, source: ImportSource, hint: str | None = None
    ) -> tuple[ImportAdapter, Detection]:
        if hint and hint.strip().lower() not in AUTO_HINTS:
            adapter = self.find(hint)
            if adapter is None:
                raise unsupported_format(
                    f"未知的格式提示：{hint}", details={"hintFormat": hint}
                )
            if not adapter.supported:
                raise _unsupported_placeholder(adapter)
            detection = adapter.detect(source)
            if detection is not None and detection.confidence > 0:
                return adapter, detection
            # 提示不匹配实际内容时继续自动探测，避免 UI 的默认值挡住正确格式。

        best: tuple[ImportAdapter, Detection] | None = None
        for adapter in self._adapters:
            if not adapter.supported:
                continue
            detection = adapter.detect(source)
            if detection is None or detection.confidence <= 0:
                continue
            if best is None or detection.confidence > best[1].confidence:
                best = (adapter, detection)
        if best is None:
            raise unsupported_format(
                "无法识别文件格式（当前支持 WFDB 与 CSV）",
                details={"adapters": [a.info() for a in self._adapters]},
            )
        return best


def _unsupported_placeholder(adapter: ImportAdapter) -> UnsupportedFormatError:
    return unsupported_format(
        f"{adapter.format} 格式尚未支持：等待真实样本，B3 实现",
        details={
            "adapterId": adapter.adapter_id,
            "format": adapter.format,
            "supported": False,
        },
    )


def build_default_registry() -> AdapterRegistry:
    from .csv_adapter import CsvImportAdapter
    from .placeholders import placeholder_adapters
    from .wfdb_adapter import WfdbImportAdapter

    registry = AdapterRegistry([WfdbImportAdapter(), CsvImportAdapter()])
    for adapter in placeholder_adapters():
        registry.register(adapter)
    return registry


__all__ = ["AdapterRegistry", "build_default_registry"]

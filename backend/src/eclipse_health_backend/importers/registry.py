"""格式注册与按置信度探测。

顺序：WFDB → CSV → 厂商/设备格式。所有适配器都参与自动探测，
按置信度取最高；置信度完全相同时返回 ``ambiguous_format``，提示用户用
``hintFormat`` 明确选择，不替用户猜。
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import Detection, ImportAdapter, ImportSource
from .errors import ImportApiError, UnsupportedFormatError, unsupported_format

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

    def _detections(self, source: ImportSource) -> list[tuple[ImportAdapter, Detection]]:
        found: list[tuple[ImportAdapter, Detection]] = []
        for adapter in self._adapters:
            if not adapter.supported:
                continue
            detection = adapter.detect(source)
            if detection is not None and detection.confidence > 0:
                found.append((adapter, detection))
        found.sort(key=lambda item: item[1].confidence, reverse=True)
        return found

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

        found = self._detections(source)
        if not found:
            raise unsupported_format(
                "无法识别文件格式（支持 WFDB / CSV / EDF / SCP-ECG / Apple 健康导出 / 小米运动 / Samsung / 华为）",
                details={"adapters": [a.info() for a in self._adapters]},
            )
        best = found[0]
        tied = [
            (adapter, detection)
            for adapter, detection in found[1:]
            if abs(detection.confidence - best[1].confidence) < 1e-9
        ]
        if tied:
            candidates = [
                {
                    "adapterId": adapter.adapter_id,
                    "format": adapter.format,
                    "confidence": detection.confidence,
                    "reason": detection.reason,
                }
                for adapter, detection in [best, *tied]
            ]
            raise ImportApiError(
                "多个格式的匹配置信度相同，请用 hintFormat 指定",
                code="ambiguous_format",
                details={"candidates": candidates},
            )
        return best


def _unsupported_placeholder(adapter: ImportAdapter) -> UnsupportedFormatError:
    return unsupported_format(
        f"{adapter.format} 格式尚未支持：等待真实样本",
        details={
            "adapterId": adapter.adapter_id,
            "format": adapter.format,
            "supported": False,
        },
    )


def build_default_registry() -> AdapterRegistry:
    from .apple_adapter import AppleImportAdapter
    from .apple_health_adapter import AppleHealthAdapter
    from .csv_adapter import CsvImportAdapter
    from .edf_adapter import EdfImportAdapter
    from .huawei_adapter import HuaweiImportAdapter
    from .placeholders import placeholder_adapters
    from .samsung_adapter import SamsungImportAdapter
    from .scp_ecg_adapter import ScpEcgImportAdapter
    from .wfdb_adapter import WfdbImportAdapter
    from .xiaomi_adapter import XiaomiAdapter

    registry = AdapterRegistry(
        [
            WfdbImportAdapter(),
            CsvImportAdapter(),
            EdfImportAdapter(),
            ScpEcgImportAdapter(),
            AppleImportAdapter(),
            AppleHealthAdapter(),
            XiaomiAdapter(),
            SamsungImportAdapter(),
            HuaweiImportAdapter(),
        ]
    )
    for adapter in placeholder_adapters():
        registry.register(adapter)
    return registry


__all__ = ["AdapterRegistry", "build_default_registry"]

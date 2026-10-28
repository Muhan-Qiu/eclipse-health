"""WFDB 适配器：MIT-BIH 等 PhysioNet 记录。

- 输入可以是文件夹、``.zip``、``.hea``（自动找同名 ``.dat``/``.atr``）；
- 优先 MLII，否则第一导联；物理单位统一换算到 mV；
- 非 360 Hz 保留原采样率并在 preview 标记 ``requires.samplingRate``；
- ``.atr`` 只作为参考 R 峰记录 ``hasAnnotations``/数量，不当诊断标签。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import (
    TARGET_FS,
    Detection,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    finalize_parsed,
    normalize_lead_name,
    normalize_unit,
    unit_scale,
    warning,
)
from .errors import ImportApiError, invalid_file

MAX_PREVIEW_SAMPLES = 2000


class WfdbImportAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.wfdb"
    adapter_version = "1.0.0"
    format = "wfdb"

    # ---------------------------------------------------------------- detect
    def _header_files(self, source: ImportSource) -> list[Path]:
        if source.extracted_dir is not None:
            return sorted(source.extracted_dir.rglob("*.hea"))
        path = source.path
        if path.is_dir():
            return sorted(path.glob("*.hea"))
        if path.suffix.lower() == ".hea":
            return [path]
        sibling = path.with_suffix(".hea")
        return [sibling] if sibling.is_file() else []

    def detect(self, source: ImportSource) -> Detection | None:
        headers = self._header_files(source)
        if not headers:
            return None
        suffix = source.path.suffix.lower()
        if source.extracted_dir is not None or suffix == ".hea" or source.path.is_dir():
            return Detection(self.format, 1.0, "找到 WFDB .hea 头文件")
        return Detection(self.format, 0.9, "找到同名 .hea 头文件")

    def _resolve_prefix(self, source: ImportSource) -> Path:
        headers = self._header_files(source)
        if not headers:
            raise invalid_file("未找到 WFDB .hea 头文件")
        if len(headers) > 1:
            raise invalid_file(
                "目录或压缩包里有多个 WFDB 记录，请直接选择 .hea 文件",
                details={"candidates": [item.name for item in headers]},
            )
        return headers[0].with_suffix("")

    # ---------------------------------------------------------------- preview
    def _read_header(self, prefix: Path) -> Any:
        import wfdb

        try:
            return wfdb.rdheader(str(prefix))
        except Exception as exc:
            raise invalid_file(
                "无法读取 WFDB 头文件", details={"reason": str(exc)}
            ) from exc

    def _read_digital(
        self, prefix: Path, *, samp_to: int | None, header: Any
    ) -> tuple[np.ndarray, list[float], list[float]]:
        import wfdb

        options: dict[str, Any] = {"physical": False}
        if samp_to is not None:
            options["sampfrom"] = 0
            options["sampto"] = max(1, min(int(samp_to), int(header.sig_len)))
        try:
            record = wfdb.rdrecord(str(prefix), **options)
        except Exception as exc:
            raise invalid_file(
                "无法读取 WFDB 波形", details={"reason": str(exc)}
            ) from exc
        if record.d_signal is None or record.d_signal.size == 0:
            raise invalid_file("WFDB 记录没有波形数据")
        gains = [
            float(value) if value else 1.0 for value in (record.adc_gain or [])
        ]
        baselines = [float(value) for value in (record.baseline or [])]
        channels = int(record.d_signal.shape[1])
        gains = (gains + [1.0] * channels)[:channels]
        baselines = (baselines + [0.0] * channels)[:channels]
        return np.asarray(record.d_signal, dtype=np.float64), gains, baselines

    @staticmethod
    def _lead_units(header: Any, channels: int) -> list[str | None]:
        raw = header.units
        units = [raw] if isinstance(raw, str) else list(raw or [])
        return [(str(units[i]) if i < len(units) else None) for i in range(channels)]

    @staticmethod
    def _primary_index(names: list[str]) -> int:
        upper = [name.upper() for name in names]
        return upper.index("MLII") if "MLII" in upper else 0

    def preview(self, source: ImportSource) -> PreviewData:
        prefix = self._resolve_prefix(source)
        header = self._read_header(prefix)
        names = [str(name) for name in (header.sig_name or [])]
        if not names:
            raise invalid_file("WFDB 头文件缺少导联信息")
        fs = float(header.fs)
        if fs <= 0 or int(header.sig_len) <= 0:
            raise invalid_file("WFDB 头文件的采样率或长度非法")

        channels = len(names)
        units = self._lead_units(header, channels)
        normalized_units = [normalize_unit(unit) for unit in units]
        requires_unit = any(unit is None for unit in normalized_units)

        primary = self._primary_index(names)
        declared = normalized_units[primary] or "mV"
        digital, gains, baselines = self._read_digital(
            prefix, samp_to=MAX_PREVIEW_SAMPLES, header=header
        )
        scale = unit_scale(declared) or 1.0
        column = (digital[:, primary] - baselines[primary]) / gains[primary] * scale
        samples = [float(value) for value in np.asarray(column, dtype=np.float64)]

        warnings: list[dict[str, Any]] = []
        if abs(fs - TARGET_FS) > 1e-6:
            warnings.append(
                warning(
                    "non_target_sampling_rate",
                    f"采样率 {fs:g} Hz，分析引擎以 360 Hz 为基准，提交时需确认",
                    severity="warning",
                )
            )
        if channels > 1:
            warnings.append(
                warning(
                    "multi_lead",
                    f"文件含 {channels} 个导联，将全部入库",
                    severity="info",
                )
            )
        if requires_unit:
            warnings.append(
                warning(
                    "unknown_units",
                    "头文件未给出可识别的单位（mV/uV/V），提交时需指定",
                    severity="warning",
                )
            )
        has_annotations, count = self._annotation_info(prefix)

        return PreviewData(
            sampling_rate=fs,
            leads=[normalize_lead_name(name, index) for index, name in enumerate(names)],
            duration_sec=int(header.sig_len) / fs,
            unit="mV",
            requires_sampling_rate=abs(fs - TARGET_FS) > 1e-6,
            requires_lead=False,
            requires_unit=requires_unit,
            warnings=warnings,
            n_samples=int(header.sig_len),
            samples=samples[:MAX_PREVIEW_SAMPLES],
            has_annotations=has_annotations,
            annotation_count=count,
        )

    # ------------------------------------------------------------------ parse
    def _annotation_info(self, prefix: Path) -> tuple[bool, int]:
        import wfdb

        try:
            annotations = wfdb.rdann(str(prefix), "atr")
        except Exception:  # noqa: BLE001 - 标注可选
            return False, 0
        count = len(annotations.sample) if annotations.sample is not None else 0
        return count > 0, count

    def _reference_annotations(
        self, prefix: Path, n_samples: int
    ) -> list[tuple[int, str]] | None:
        import wfdb

        try:
            annotations = wfdb.rdann(str(prefix), "atr")
        except Exception:  # noqa: BLE001
            return None
        if annotations.sample is None:
            return None
        pairs = sorted(
            {
                (int(pos), str(symbol))
                for pos, symbol in zip(annotations.sample, annotations.symbol)
                if 0 <= int(pos) < n_samples
            }
        )
        return pairs or None

    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        prefix = self._resolve_prefix(source)
        header = self._read_header(prefix)
        names = [str(name) for name in (header.sig_name or [])]
        if not names:
            raise invalid_file("WFDB 头文件缺少导联信息")
        fs = float(header.fs)
        if fs <= 0:
            raise invalid_file("WFDB 头文件采样率非法")

        channels = len(names)
        units = self._lead_units(header, channels)
        normalized_units = [normalize_unit(unit) for unit in units]

        correction = None
        if parameters.unit:
            wanted = unit_scale(parameters.unit)
            if wanted is None:
                raise ImportApiError(
                    "无法识别的单位参数（可用 mV/uV/V）",
                    code="invalid_parameter",
                    details={"unit": parameters.unit},
                )
            correction = wanted

        digital, gains, baselines = self._read_digital(prefix, samp_to=None, header=header)
        n_samples = int(digital.shape[0])
        if n_samples == 0:
            raise invalid_file("WFDB 记录没有采样点")

        leads: list[ParsedLead] = []
        for index, name in enumerate(names):
            declared_unit = normalized_units[index] or "mV"
            declared_scale = unit_scale(declared_unit) or 1.0
            # parameters.unit 声明的是「文件原始单位」；给了就以它为准，
            # 否则按头文件单位换算到 mV。
            factor = correction if correction is not None else declared_scale
            column = (digital[:, index] - baselines[index]) / gains[index]
            samples = column * factor
            leads.append(
                ParsedLead(
                    lead=normalize_lead_name(name, index),
                    samples=samples,
                    digital=digital[:, index],
                    gain=gains[index],
                )
            )

        primary = self._primary_index(names)
        primary_lead = normalize_lead_name(names[primary], primary)
        has_annotations, count = self._annotation_info(prefix)
        parsed = ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=fs,
            duration_sec=n_samples / fs,
            leads=leads,
            primary_lead=primary_lead,
            source_unit=normalized_units[primary] or "mV",
            has_annotations=has_annotations,
            annotation_count=count,
            reference_annotations=(
                self._reference_annotations(prefix, n_samples) if has_annotations else None
            ),
            metadata={
                "adapterId": self.adapter_id,
                "format": self.format,
                "sourceUnit": normalized_units[primary] or "mV",
                "channelCount": channels,
                "hasAnnotations": has_annotations,
                "annotationCount": count,
            },
            warnings=[],
        )
        return finalize_parsed(parsed, parameters)


__all__ = ["WfdbImportAdapter"]

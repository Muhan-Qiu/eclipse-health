"""CSV 适配器：自动识别分隔符、表头、时间/索引列与单导联列。

不硬猜：无法确定导联或采样率时在 preview 标 ``requires``，由用户校正后再提交。
编码容错顺序 UTF-8(BOM) → GB18030(含 GBK) → Latin-1；解析失败给出原始行列号。
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from .base import (
    LEAD_ALIASES,
    Detection,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    detect_unit_in_text,
    finalize_parsed,
    normalize_lead_name,
    normalize_unit,
    unit_scale,
    warning,
)
from .errors import ImportApiError, invalid_file

MAX_PREVIEW_SAMPLES = 2000
TEXT_SUFFIXES = {".csv", ".tsv", ".txt"}
DELIMITERS = (",", ";", "\t", "|")
ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")

TIME_TOKENS = {
    "time",
    "times",
    "t",
    "ts",
    "timestamp",
    "sec",
    "secs",
    "second",
    "seconds",
    "elapsed",
    "时间",
    "时间s",
}
TIME_MS_TOKENS = {"ms", "msec", "millisecond", "milliseconds", "timems", "时间ms"}
INDEX_TOKENS = {
    "index",
    "idx",
    "sample",
    "samples",
    "n",
    "no",
    "number",
    "序号",
    "sampleindex",
}
GENERIC_LEAD_TOKENS = {"ecg", "ekg", "signal", "voltage", "lead", "channel", "心电"}
_LEAD_SHAPE_RE = re.compile(r"^(?:mlii|i{1,3}|av[rlf]|v[1-6])$")
_UNIT_ANNOTATION_RE = re.compile(
    r"[\(\[]\s*(?:mv|uv|µv|μv|v|millivolt|microvolt|volt)\s*[\)\]]", re.IGNORECASE
)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]", "", str(text).lower())


def _lead_token(name: str) -> str:
    return _compact(_UNIT_ANNOTATION_RE.sub(" ", str(name)))


def _is_float(token: str) -> bool:
    try:
        return math.isfinite(float(token))
    except (TypeError, ValueError):
        return False


def _clean_field(token: str) -> str:
    return token.strip().strip('"').strip("'")


def _split(line: str, delimiter: str | None) -> list[str]:
    if delimiter is None:
        return [part for part in re.split(r"[ \t]+", line.strip()) if part]
    return [_clean_field(part) for part in line.split(delimiter)]


class CsvImportAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.csv"
    adapter_version = "1.0.0"
    format = "csv"

    # ---------------------------------------------------------------- detect
    def _candidates(self, source: ImportSource) -> list[Path]:
        if source.extracted_dir is not None:
            return [
                path
                for path in sorted(source.extracted_dir.rglob("*"))
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
            ]
        path = source.path
        if path.is_dir():
            return [
                item
                for item in sorted(path.iterdir())
                if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES
            ]
        if path.suffix.lower() in TEXT_SUFFIXES:
            return [path]
        return []

    @staticmethod
    def _looks_like_table(path: Path) -> bool:
        try:
            head = path.read_bytes()[:8192]
        except OSError:
            return False
        if b"\x00" in head:
            return False
        text = None
        for encoding in ENCODINGS[:-1]:
            try:
                text = head.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = head.decode("latin-1")
        lines = [line for line in text.splitlines()[:10] if line.strip()]
        if len(lines) < 2:
            return False
        for line in lines:
            for delimiter in DELIMITERS:
                parts = [part for part in line.split(delimiter) if part.strip()]
                if len(parts) >= 2 and _is_float(_clean_field(parts[0])):
                    return True
        return _is_float(_clean_field(lines[0]))

    def detect(self, source: ImportSource) -> Detection | None:
        candidates = self._candidates(source)
        if candidates:
            return Detection(self.format, 0.9, "扩展名为 CSV/TSV/TXT")
        if source.path.is_file() and self._looks_like_table(source.path):
            return Detection(self.format, 0.6, "内容是带分隔符的数值表格")
        return None

    def _pick_file(self, source: ImportSource) -> Path:
        candidates = self._candidates(source)
        if not candidates and source.path.is_file() and self._looks_like_table(source.path):
            return source.path
        if not candidates:
            raise invalid_file("未找到 CSV 文件")
        if len(candidates) > 1:
            raise invalid_file(
                "目录或压缩包里有多个 CSV 文件，请只保留一个",
                details={"candidates": [item.name for item in candidates]},
            )
        return candidates[0]

    # ------------------------------------------------------------ text table
    def _load_text(self, path: Path) -> tuple[list[str], str, list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise invalid_file("无法读取文件", details={"reason": str(exc)}) from exc
        if b"\x00" in raw[:8192]:
            raise invalid_file("文件包含二进制内容，无法按 CSV 解析")
        text = None
        encoding_used = ""
        for encoding in ENCODINGS:
            try:
                text = raw.decode(encoding)
                encoding_used = encoding
                break
            except UnicodeDecodeError:
                continue
        if text is None:  # pragma: no cover - latin-1 不会失败
            raise invalid_file("无法解码文本文件")
        if encoding_used not in {"utf-8", "utf-8-sig"}:
            warnings.append(
                warning(
                    "fallback_encoding",
                    f"按 {encoding_used} 解码（非 UTF-8）",
                    severity="warning",
                )
            )
        return text.splitlines(), encoding_used, warnings

    @staticmethod
    def _sniff_delimiter(lines: list[str]) -> str | None:
        sample = [line for line in lines[:100] if line.strip() and not line.lstrip().startswith("#")]
        sample = sample[:20]
        best: tuple[tuple[int, int], str] | None = None
        for delimiter in DELIMITERS:
            counts = [len(_split(line, delimiter)) for line in sample]
            if not counts:
                continue
            modal = max(set(counts), key=counts.count)
            if modal < 2:
                continue
            consistency = sum(1 for count in counts if count == modal)
            score = (consistency, modal)
            if best is None or score > best[0]:
                best = (score, delimiter)
        return best[1] if best else None

    @staticmethod
    def _find_data_start(lines: list[str], delimiter: str | None) -> int:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = _split(stripped, delimiter)
            if fields and all(_is_float(token) for token in fields):
                return index
        raise invalid_file("文件里找不到数值数据行")

    def _read_table(
        self, path: Path
    ) -> tuple[np.ndarray, list[str] | None, str, list[dict[str, Any]]]:
        lines, encoding, warnings = self._load_text(path)
        delimiter = self._sniff_delimiter(lines)
        start = self._find_data_start(lines, delimiter)

        header: list[str] | None = None
        for index in range(start - 1, -1, -1):
            candidate = lines[index].strip()
            if not candidate or candidate.startswith("#"):
                continue
            header = _split(candidate, delimiter)
            break

        rows: list[list[float]] = []
        n_cols: int | None = None
        for index in range(start, len(lines)):
            line = lines[index]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = _split(stripped, delimiter)
            if n_cols is None:
                n_cols = len(fields)
            elif len(fields) != n_cols:
                raise invalid_file(
                    "CSV 行的列数不一致",
                    details={
                        "row": index + 1,
                        "expectedColumns": n_cols,
                        "actualColumns": len(fields),
                    },
                )
            values: list[float] = []
            for column, token in enumerate(fields):
                try:
                    value = float(token)
                except ValueError:
                    raise invalid_file(
                        "单元格不是数字",
                        details={"row": index + 1, "column": column + 1, "value": token[:64]},
                    ) from None
                if not math.isfinite(value):
                    raise invalid_file(
                        "单元格不是有限数值",
                        details={"row": index + 1, "column": column + 1, "value": token[:64]},
                    )
                values.append(value)
            rows.append(values)

        if not rows:
            raise invalid_file("文件里没有可解析的数值行")
        array = np.asarray(rows, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(-1, 1)

        if header is not None and len(header) != array.shape[1]:
            raise invalid_file(
                "表头列数与数据列数不一致",
                details={
                    "headerColumns": len(header),
                    "dataColumns": int(array.shape[1]),
                },
            )
        return array, header, encoding, warnings

    # ---------------------------------------------------------- column logic
    def _resolve_column(self, value: str | None, header: list[str] | None, n_cols: int) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if re.fullmatch(r"\d+", text):
            index = int(text)
            if 0 <= index < n_cols:
                return index
            raise ImportApiError(
                "列索引超出范围",
                code="invalid_parameter",
                details={"column": text, "columns": n_cols},
            )
        if header:
            wanted = _compact(text)
            for index, name in enumerate(header):
                if _compact(name) == wanted:
                    return index
        raise ImportApiError(
            "未找到指定的列", code="invalid_parameter", details={"column": text}
        )

    @staticmethod
    def _header_role(header: list[str]) -> tuple[int | None, bool]:
        """返回 (时间/索引列, 是否时间列而非索引列)。"""
        for index, name in enumerate(header):
            token = _compact(name)
            if token in TIME_TOKENS or token in TIME_MS_TOKENS:
                return index, True
        for index, name in enumerate(header):
            if _compact(name) in INDEX_TOKENS:
                return index, False
        return None, False

    @staticmethod
    def _lead_hint(header: list[str], skip: int | None) -> int | None:
        for index, name in enumerate(header):
            if index == skip:
                continue
            token = _lead_token(name)
            if token in LEAD_ALIASES or token in GENERIC_LEAD_TOKENS or _LEAD_SHAPE_RE.match(token):
                return index
        return None

    @staticmethod
    def _lead_name(name: str | None, index: int) -> str:
        if not name:
            return normalize_lead_name(None, index)
        token = _lead_token(name)
        if token in LEAD_ALIASES:
            return LEAD_ALIASES[token]
        if token in GENERIC_LEAD_TOKENS or (token.startswith("ecg") and token[3:].isdigit()):
            return "ECG"
        if token.startswith("lead") and token[4:] in LEAD_ALIASES:
            return LEAD_ALIASES[token[4:]]
        if _LEAD_SHAPE_RE.match(token):
            return LEAD_ALIASES.get(token, normalize_lead_name(name, index))
        return normalize_lead_name(name, index)

    @staticmethod
    def _sampling_rate(
        values: np.ndarray, is_time: bool, header: list[str] | None, column: int
    ) -> float | None:
        if not is_time or values.size < 2:
            return None
        diffs = np.diff(values[: min(values.size, 2000)])
        if diffs.size == 0 or not np.all(diffs > 0):
            return None
        median = float(np.median(diffs))
        if median <= 0:
            return None
        token = _compact(header[column]) if header and column < len(header) else ""
        looks_like_ms = (
            token in TIME_MS_TOKENS
            or token.endswith("ms")
            or "millisecond" in token
            or median > 0.5
        )
        rate = 1000.0 / median if looks_like_ms else 1.0 / median
        return round(rate, 6)

    def _analyze(
        self, source: ImportSource, parameters: ParseParameters | None = None
    ) -> dict[str, Any]:
        path = self._pick_file(source)
        array, header, encoding, warnings = self._read_table(path)
        n_rows, n_cols = array.shape
        params = parameters or ParseParameters()

        time_col = self._resolve_column(params.time_column, header, n_cols)
        is_time = True
        if time_col is None and header is not None:
            time_col, is_time = self._header_role(header)
        elif time_col is None:
            for column in range(n_cols):
                column_values = array[: min(n_rows, 50), column]
                if column_values.size >= 2 and np.all(np.diff(column_values) > 0):
                    time_col = column
                    is_time = not (
                        column_values.size >= 2
                        and np.all(np.diff(column_values) == 1)
                    )
                    break

        lead_col = self._resolve_column(params.lead_column, header, n_cols)
        lead_confident = lead_col is not None
        if lead_col is None and header is not None:
            hinted = self._lead_hint(header, time_col)
            if hinted is not None:
                lead_col = hinted
                lead_confident = True
        if lead_col is None:
            for column in range(n_cols):
                if column != time_col:
                    lead_col = column
                    break
        if lead_col is None:
            lead_col = 0

        detected_unit = None
        if header is not None and lead_col < len(header):
            detected_unit = detect_unit_in_text(header[lead_col])
        detected_unit = detected_unit or params.unit
        unit = normalize_unit(detected_unit) if detected_unit else None
        unit_confident = unit is not None

        sampling_rate = None
        if time_col is not None and time_col != lead_col:
            sampling_rate = self._sampling_rate(array[:, time_col], is_time, header, time_col)
        if params.sampling_rate:
            sampling_rate = float(params.sampling_rate)

        lead_name = (
            self._lead_name(header[lead_col] if header and lead_col < len(header) else None, lead_col)
            if lead_confident
            else None
        )

        return {
            "path": path,
            "array": array,
            "header": header,
            "encoding": encoding,
            "warnings": warnings,
            "n_rows": n_rows,
            "n_cols": n_cols,
            "time_col": time_col,
            "lead_col": lead_col,
            "lead_confident": lead_confident,
            "lead_name": lead_name,
            "unit": unit,
            "unit_confident": unit_confident,
            "sampling_rate": sampling_rate,
        }

    # ---------------------------------------------------------------- preview
    def preview(self, source: ImportSource) -> PreviewData:
        info = self._analyze(source)
        array: np.ndarray = info["array"]
        lead_col: int = info["lead_col"]
        unit: str | None = info["unit"]
        sampling_rate: float | None = info["sampling_rate"]

        warnings = list(info["warnings"])
        if sampling_rate is not None and abs(sampling_rate - 360.0) > 1e-6:
            warnings.append(
                warning(
                    "non_target_sampling_rate",
                    f"采样率 {sampling_rate:g} Hz，分析引擎以 360 Hz 为基准",
                    severity="warning",
                )
            )
        if not info["lead_confident"]:
            warnings.append(
                warning(
                    "lead_unknown",
                    "无法从表头确定导联，提交时需指定",
                    severity="warning",
                )
            )
        if not info["unit_confident"]:
            warnings.append(
                warning(
                    "unit_unknown",
                    "表头未标注单位，提交时需确认（默认按 mV 预览）",
                    severity="warning",
                )
            )
        if sampling_rate is None:
            warnings.append(
                warning(
                    "sampling_rate_unknown",
                    "没有时间列，无法推算采样率，提交时需指定",
                    severity="warning",
                )
            )

        scale = unit_scale(unit) if unit else 1.0
        values = np.asarray(array[:MAX_PREVIEW_SAMPLES, lead_col], dtype=np.float64) * (
            scale or 1.0
        )
        duration = (
            float(info["n_rows"]) / sampling_rate if sampling_rate else None
        )
        leads = [info["lead_name"]] if info["lead_confident"] else []

        return PreviewData(
            sampling_rate=sampling_rate,
            leads=leads,
            duration_sec=duration,
            unit="mV",
            requires_sampling_rate=sampling_rate is None,
            requires_lead=not info["lead_confident"],
            requires_unit=not info["unit_confident"],
            warnings=warnings,
            n_samples=int(info["n_rows"]),
            samples=[float(value) for value in values],
        )

    # ------------------------------------------------------------------ parse
    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        info = self._analyze(source, parameters)
        array: np.ndarray = info["array"]
        lead_col: int = info["lead_col"]
        sampling_rate: float | None = info["sampling_rate"]
        if sampling_rate is None:
            raise ImportApiError(
                "缺少采样率，请用 parameters.samplingRate 指定",
                code="sampling_rate_required",
            )

        unit = info["unit"] or parameters.unit or "mV"
        scale = unit_scale(unit)
        if scale is None:
            raise ImportApiError(
                "无法识别的单位（可用 mV/uV/V）",
                code="invalid_parameter",
                details={"unit": unit},
            )

        if not info["lead_confident"] and not parameters.lead:
            raise ImportApiError(
                "无法确定导联，请用 parameters.lead 指定",
                code="lead_required",
                details={"columns": int(info["n_cols"])},
            )

        lead_name = (
            normalize_lead_name(parameters.lead, 0)
            if parameters.lead
            else (info["lead_name"] or normalize_lead_name(None, lead_col))
        )
        samples = np.asarray(array[:, lead_col], dtype=np.float64) * scale
        n_samples = int(samples.size)

        parsed = ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=float(sampling_rate),
            duration_sec=n_samples / float(sampling_rate),
            leads=[
                ParsedLead(
                    lead=lead_name,
                    samples=samples,
                    # 与 analysis.ingest 保持一致：无真实 ADC 时按 gain=200 映射。
                    digital=samples * 200.0,
                    gain=200.0,
                )
            ],
            primary_lead=lead_name,
            source_unit=unit,
            metadata={
                "adapterId": self.adapter_id,
                "format": self.format,
                "sourceUnit": unit,
                "encoding": info["encoding"],
                "columnCount": int(info["n_cols"]),
                "hasAnnotations": False,
                "annotationCount": 0,
            },
            warnings=list(info["warnings"]),
        )
        if not parameters.lead and not info["lead_confident"]:
            parsed.warnings.append(
                warning("lead_assumed", "导联名由文件列顺序推断", severity="warning")
            )
        return finalize_parsed(parsed, parameters)


__all__ = ["CsvImportAdapter"]

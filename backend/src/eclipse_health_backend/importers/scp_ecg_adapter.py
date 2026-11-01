"""SCP-ECG 适配器：按 EN 1064 的真实段结构做最小可用解析。

结构（已用公开样本验证）：
- 文件头 6 字节：CRC u16 + 文件长度 u32；
- 段头 16 字节：CRC u16 + 段号 u16 + 段长 u32 + 段版本 + 协议版本 + 6 字节保留；
- section 0 指针：每项 10 字节（段号 u16、段长 u32、文件偏移 u32，偏移从 1 开始）；
- section 2：Huffman 表（19999 = 标准默认表，0 = 原始 16-bit）；
- section 3：导联数量/标志 + 每导联 9 字节（起始样本 u32、结束样本 u32、导联 ID u8）；
- section 6：AVM(u16, nV/LSB)、采样间隔(µs)、编码(0/1/2 差分)、压缩标志、每导联字节数、样本。

只支持同时记录、从样本 1 开始、无参考搏动减法的文件；其余变体明确返回
``unsupported_section``。数据按 AVM 换算到 mV，单位不依赖用户猜测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .base import (
    Detection,
    ImportAdapter,
    ImportSource,
    ParsedImport,
    ParsedLead,
    ParseParameters,
    PreviewData,
    finalize_parsed,
    normalize_unit,
    unit_scale,
    warning,
)
from .errors import ImportApiError, invalid_file

MAX_PREVIEW_SAMPLES = 2000
MAX_LEADS = 16
FILE_HEADER_BYTES = 6
SECTION_HEADER_BYTES = 16
POINTER_BYTES = 10
DEFAULT_HUFFMAN_MARKER = 19_999

# EN 1064 §5.6.5 的常用导联 ID；未列出的保留原始 ID 作 L<id>。
SCP_LEAD_NAMES: dict[int, str] = {
    1: "I",
    2: "II",
    3: "V1",
    4: "V2",
    5: "V3",
    6: "V4",
    7: "V5",
    8: "V6",
    9: "V7",
    10: "V2R",
    11: "V3R",
    12: "V4R",
    13: "V5R",
    14: "V6R",
    15: "V7R",
    16: "X",
    17: "Y",
    18: "Z",
    19: "CC5",
    20: "CM5",
    24: "I-Frank",
    25: "E",
    26: "C",
    27: "A",
    28: "M",
    29: "F",
    30: "H",
    61: "III",
    62: "aVR",
    63: "aVL",
    64: "aVF",
    65: "aVRneg",
    66: "V8",
    67: "V9",
}

# 默认 Huffman 表（与公开实现一致）：键为码字，值为 (是否为字面量, 值/位宽)。
DEFAULT_HUFFMAN: dict[str, tuple[bool, int]] = {
    "0": (True, 0),
    "100": (True, 1),
    "101": (True, -1),
    "1100": (True, 2),
    "1101": (True, -2),
    "11100": (True, 3),
    "11101": (True, -3),
    "111100": (True, 4),
    "111101": (True, -4),
    "1111100": (True, 5),
    "1111101": (True, -5),
    "11111100": (True, 6),
    "11111101": (True, -6),
    "111111100": (True, 7),
    "111111101": (True, -7),
    "1111111100": (True, 8),
    "1111111101": (True, -8),
    "1111111110": (False, 8),
    "1111111111": (False, 16),
}


@dataclass(slots=True)
class ScpSection:
    section_id: int
    length: int
    version: int
    protocol: int
    body: bytes


@dataclass(slots=True)
class ScpLead:
    lead_id: int
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass(slots=True)
class ScpData:
    path: Path
    sampling_rate: float
    interval_us: int
    amplitude_multiplier_nv: int
    encoding: int
    digital: list[np.ndarray]
    leads: list[str]
    leads_confident: bool
    sections: dict[int, ScpSection]
    protocol_version: int | None
    section_version: int | None
    huffman: bool
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _u16(blob: bytes, offset: int) -> int:
    return int.from_bytes(blob[offset : offset + 2], "little", signed=False)


def _u32(blob: bytes, offset: int) -> int:
    return int.from_bytes(blob[offset : offset + 4], "little", signed=False)


def _unsupported(message: str, **details: Any) -> ImportApiError:
    return ImportApiError(message, code="unsupported_section", details=details)


def _decode_default_huffman(raw: bytes) -> np.ndarray:
    bits = "".join(f"{byte:08b}" for byte in raw)
    values: list[int] = []
    index = 0
    total = len(bits)
    while index < total:
        end = index + 1
        matched = False
        while end <= total:
            entry = DEFAULT_HUFFMAN.get(bits[index:end])
            if entry is not None:
                literal, value = entry
                if literal:
                    values.append(value)
                    index = end
                else:
                    start = end
                    end = start + value
                    if end > total:
                        raise _unsupported(
                            "SCP-ECG Huffman 码流在 16-bit 字面量中间结束",
                            section=6,
                        )
                    bits_value = bits[start:end]
                    number = int(bits_value[1:], base=2)
                    if bits_value[0] == "1":
                        number -= 1 << (len(bits_value) - 1)
                    values.append(number)
                    index = end
                matched = True
                break
            end += 1
        if not matched:
            raise _unsupported("SCP-ECG Huffman 码流无法匹配默认表", section=6)
    return np.asarray(values, dtype=np.int64)


class ScpEcgImportAdapter(ImportAdapter):
    adapter_id = "org.eclipsehealth.scp-ecg"
    adapter_version = "1.0.0"
    format = "scp-ecg"

    # ---------------------------------------------------------------- detect
    def _candidates(self, source: ImportSource) -> list[Path]:
        def _files(root: Path) -> list[Path]:
            return sorted(
                path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".scp"
            )

        if source.extracted_dir is not None:
            return _files(source.extracted_dir)
        if source.path.is_dir():
            return _files(source.path)
        if source.path.suffix.lower() == ".scp":
            return [source.path]
        return []

    @staticmethod
    def _magic(path: Path) -> bool:
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                head = handle.read(24)
        except OSError:
            return False
        if len(head) < 22 or size < 22:
            return False
        declared = _u32(head, 2)
        section_id = _u16(head, 6 + 2)
        section_length = _u32(head, 6 + 4)
        return (
            section_id == 0
            and 22 <= declared <= max(size, 22)
            and SECTION_HEADER_BYTES <= section_length <= size
        )

    def detect(self, source: ImportSource) -> Detection | None:
        candidates = self._candidates(source)
        if candidates:
            return Detection(self.format, 1.0, "扩展名为 .scp")
        if source.path.is_file() and self._magic(source.path):
            return Detection(self.format, 0.75, "内容符合 SCP-ECG 文件/段头特征")
        return None

    def _pick_file(self, source: ImportSource) -> Path:
        candidates = self._candidates(source)
        if not candidates and source.path.is_file() and self._magic(source.path):
            return source.path
        if not candidates:
            raise invalid_file("未找到 SCP-ECG 文件")
        if len(candidates) > 1:
            raise invalid_file(
                "目录或压缩包里有多个 SCP-ECG 文件，请只保留一个",
                details={"candidates": [item.name for item in candidates]},
            )
        return candidates[0]

    # --------------------------------------------------------------- sections
    @staticmethod
    def _section_header(blob: bytes, offset: int) -> tuple[int, int, int, int, int]:
        if offset + SECTION_HEADER_BYTES > len(blob):
            raise invalid_file("SCP-ECG 段头越界", details={"offset": offset})
        return (
            _u16(blob, offset),  # crc（不校验；部分设备写 0）
            _u16(blob, offset + 2),  # section id
            _u32(blob, offset + 4),  # section length
            blob[offset + 8],  # section version
            blob[offset + 9],  # protocol version
        )

    def _read_sections(
        self, blob: bytes, warnings: list[dict[str, Any]]
    ) -> tuple[dict[int, ScpSection], int]:
        if len(blob) < FILE_HEADER_BYTES + SECTION_HEADER_BYTES:
            raise invalid_file("SCP-ECG 文件短于文件头 + section 0 头")
        declared_length = _u32(blob, 2)
        if declared_length > len(blob):
            warnings.append(
                warning(
                    "truncated_file",
                    f"文件头声明 {declared_length} 字节，实际只有 {len(blob)} 字节",
                    severity="warning",
                )
            )
        elif declared_length < len(blob):
            warnings.append(
                warning("trailing_bytes", f"文件末尾有 {len(blob) - declared_length} 字节未声明")
            )

        _, section_id, section_length, _version, _protocol = self._section_header(
            blob, FILE_HEADER_BYTES
        )
        if section_id != 0:
            raise invalid_file(
                "SCP-ECG 第一个段不是 section 0", details={"sectionId": section_id}
            )
        if section_length < SECTION_HEADER_BYTES or FILE_HEADER_BYTES + section_length > len(blob):
            raise invalid_file(
                "SCP-ECG section 0 长度非法", details={"sectionLength": section_length}
            )

        pointer_count = (section_length - SECTION_HEADER_BYTES) // POINTER_BYTES
        if pointer_count <= 0:
            raise invalid_file("SCP-ECG section 0 没有指针")

        sections: dict[int, ScpSection] = {}
        for index in range(pointer_count):
            base = FILE_HEADER_BYTES + SECTION_HEADER_BYTES + index * POINTER_BYTES
            pointer_id = _u16(blob, base)
            pointer_length = _u32(blob, base + 2)
            pointer_index = _u32(blob, base + 6)
            if pointer_index == 0 or pointer_length == 0:
                continue
            offset = pointer_index - 1
            if offset <= 0 or offset + SECTION_HEADER_BYTES > len(blob):
                warnings.append(
                    warning(
                        "pointer_out_of_range",
                        f"section {pointer_id} 的指针 {pointer_index} 越界，已跳过",
                        severity="warning",
                    )
                )
                continue
            try:
                _, sid, length, seg_version, seg_protocol = self._section_header(blob, offset)
            except ImportApiError:
                continue
            if sid != pointer_id or length < SECTION_HEADER_BYTES:
                warnings.append(
                    warning(
                        "pointer_mismatch",
                        f"section {pointer_id} 的指针与段头不一致，已跳过",
                        severity="warning",
                    )
                )
                continue
            end = offset + min(length, len(blob) - offset)
            body = blob[offset + SECTION_HEADER_BYTES : end]
            sections[pointer_id] = ScpSection(
                section_id=sid,
                length=length,
                version=seg_version,
                protocol=seg_protocol,
                body=body,
            )
        return sections, pointer_count

    @staticmethod
    def _parse_leads(section: ScpSection) -> tuple[list[ScpLead], int, bool, bool]:
        body = section.body
        if len(body) < 2:
            raise _unsupported("SCP-ECG section 3 过短", section=3)
        lead_count = body[0]
        flags = body[1]
        if lead_count < 1 or lead_count > MAX_LEADS:
            raise _unsupported(
                "SCP-ECG section 3 导联数量不合理", section=3, leads=lead_count
            )
        if len(body) < 2 + lead_count * 9:
            raise _unsupported(
                "SCP-ECG section 3 导联定义被截断",
                section=3,
                bytes=len(body),
                leads=lead_count,
            )
        ref_subtraction = bool(flags & 0x01)
        simultaneous = bool(flags & 0x04)
        leads: list[ScpLead] = []
        for index in range(lead_count):
            base = 2 + index * 9
            start = _u32(body, base)
            end = _u32(body, base + 4)
            lead_id = body[base + 8]
            if start < 1 or end < start:
                raise _unsupported(
                    "SCP-ECG section 3 导联样本范围非法",
                    section=3,
                    lead=lead_id,
                    start=start,
                    end=end,
                )
            leads.append(ScpLead(lead_id=lead_id, start=start, end=end))
        return leads, flags, ref_subtraction, simultaneous

    def _huffman_tables(self, section: ScpSection | None) -> bool:
        if section is None or len(section.body) < 2:
            return False
        marker = _u16(section.body, 0)
        if marker == 0:
            return False
        if marker == DEFAULT_HUFFMAN_MARKER:
            return True
        raise _unsupported(
            "SCP-ECG 使用自定义 Huffman 表，暂不支持",
            section=2,
            marker=marker,
        )

    def _parse_section6(
        self,
        section: ScpSection,
        leads: list[ScpLead],
        huffman: bool,
        *,
        reference_beat_subtraction: bool,
    ) -> tuple[int, int, int, list[np.ndarray]]:
        body = section.body
        if len(body) < 6:
            raise _unsupported("SCP-ECG section 6 过短", section=6)
        amplitude_multiplier_nv = _u16(body, 0)
        interval_us = _u16(body, 2)
        encoding = body[4]
        compression = body[5]
        if interval_us == 0:
            raise _unsupported("SCP-ECG section 6 采样间隔为 0", section=6)
        if encoding not in (0, 1, 2):
            raise _unsupported("SCP-ECG section 6 编码未知", section=6, encoding=encoding)
        if compression != 0:
            raise _unsupported(
                "SCP-ECG 双模态压缩暂不支持", section=6, compression=compression
            )
        if reference_beat_subtraction:
            raise _unsupported("SCP-ECG 参考搏动减法压缩暂不支持", section=6)
        header_end = 6 + 2 * len(leads)
        if len(body) < header_end:
            raise _unsupported("SCP-ECG section 6 导联字节数被截断", section=6)
        lengths = [_u16(body, 6 + index * 2) for index in range(len(leads))]
        position = header_end
        arrays: list[np.ndarray] = []
        for lead, byte_length in zip(leads, lengths):
            if position + byte_length > len(body):
                raise _unsupported(
                    "SCP-ECG section 6 导联数据越界",
                    section=6,
                    lead=lead.lead_id,
                    bytes=byte_length,
                )
            raw = body[position : position + byte_length]
            position += byte_length
            if huffman:
                values = _decode_default_huffman(raw)
            else:
                if byte_length % 2:
                    raise _unsupported(
                        "SCP-ECG 16-bit 样本字节数为奇数",
                        section=6,
                        lead=lead.lead_id,
                        bytes=byte_length,
                    )
                values = np.frombuffer(raw, dtype="<i2").astype(np.int64)
            declared = lead.length
            if values.size < declared:
                raise _unsupported(
                    "SCP-ECG section 6 样本数少于 section 3 声明",
                    section=6,
                    lead=lead.lead_id,
                    decoded=int(values.size),
                    declared=declared,
                )
            if np.any(values[declared:] != 0):
                raise _unsupported(
                    "SCP-ECG section 6 超出声明长度的数据不是零填充",
                    section=6,
                    lead=lead.lead_id,
                    decoded=int(values.size),
                    declared=declared,
                )
            values = values[:declared]
            if encoding == 1:
                values = np.cumsum(values)
            elif encoding == 2:
                if values.size < 2:
                    raise _unsupported("SCP-ECG 二阶差分样本不足", section=6)
                initial = values[:2]
                first_derivative = np.cumsum(
                    np.concatenate([[initial[1] - initial[0]], values[2:]])
                )
                values = np.cumsum(np.concatenate([[initial[0]], first_derivative]))
            arrays.append(values.astype(np.float64))
        return amplitude_multiplier_nv, interval_us, encoding, arrays

    # ------------------------------------------------------------- analysis
    def _analyze(self, source: ImportSource) -> ScpData:
        path = self._pick_file(source)
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise invalid_file("无法读取 SCP-ECG 文件", details={"reason": str(exc)}) from exc

        warnings: list[dict[str, Any]] = []
        sections, pointer_count = self._read_sections(blob, warnings)
        if 3 not in sections:
            raise _unsupported(
                "SCP-ECG 缺少 section 3 导联定义",
                section=3,
                sections=sorted(sections),
                pointers=pointer_count,
            )
        if 6 not in sections:
            raise _unsupported(
                "SCP-ECG 缺少 section 6 节律数据段",
                section=6,
                sections=sorted(sections),
            )

        leads_info, _flags, ref_subtraction, simultaneous = self._parse_leads(sections[3])
        if not simultaneous:
            raise _unsupported("SCP-ECG 非同步记录的导联暂不支持", section=3)
        starts = {lead.start for lead in leads_info}
        if len(starts) != 1:
            raise _unsupported(
                "SCP-ECG 各导联起始样本不同",
                section=3,
                starts=sorted(starts),
            )
        lengths = {lead.length for lead in leads_info}
        if len(lengths) != 1:
            raise _unsupported(
                "SCP-ECG 各导联长度不同",
                section=3,
                lengths=sorted(lengths),
            )
        start_sample = starts.pop()
        if start_sample != 1:
            warnings.append(
                warning(
                    "scp_start_sample_offset",
                    f"导联从第 {start_sample} 个样本开始，已按文件内波形导入",
                    severity="info",
                )
            )

        huffman = self._huffman_tables(sections.get(2))

        amplitude_multiplier_nv, interval_us, encoding, arrays = self._parse_section6(
            sections[6],
            leads_info,
            huffman,
            reference_beat_subtraction=ref_subtraction,
        )
        if len(arrays) != len(leads_info):
            raise _unsupported(
                "SCP-ECG section 6 与 section 3 的导联数不一致",
                section=6,
                section6=len(arrays),
                section3=len(leads_info),
            )

        leads = [
            SCP_LEAD_NAMES.get(lead.lead_id, f"L{lead.lead_id}") for lead in leads_info
        ]
        leads_confident = all(lead.lead_id in SCP_LEAD_NAMES for lead in leads_info)
        if not leads_confident:
            warnings.append(
                warning(
                    "lead_unknown",
                    "部分 SCP-ECG 导联 ID 不在常用表中，已命名为 L<id>",
                    severity="warning",
                )
            )
        if huffman:
            warnings.append(
                warning("scp_huffman", "使用 SCP-ECG 标准 Huffman 表解码", severity="info")
            )
        if encoding:
            warnings.append(
                warning(
                    "scp_difference_encoding",
                    f"SCP-ECG 使用{'一' if encoding == 1 else '二'}阶差分编码，已还原",
                    severity="info",
                )
            )

        section1 = sections.get(1)
        return ScpData(
            path=path,
            sampling_rate=round(1_000_000.0 / interval_us, 6),
            interval_us=interval_us,
            amplitude_multiplier_nv=amplitude_multiplier_nv,
            encoding=encoding,
            digital=arrays,
            leads=leads,
            leads_confident=leads_confident,
            sections=sections,
            protocol_version=section1.protocol if section1 else None,
            section_version=section1.version if section1 else None,
            huffman=huffman,
            warnings=warnings,
        )

    # --------------------------------------------------------------- preview
    def preview(self, source: ImportSource) -> PreviewData:
        data = self._analyze(source)
        scale = data.amplitude_multiplier_nv / 1_000_000.0
        preview = data.digital[0][:MAX_PREVIEW_SAMPLES] * scale
        return PreviewData(
            sampling_rate=data.sampling_rate,
            leads=list(data.leads),
            duration_sec=len(data.digital[0]) / data.sampling_rate,
            unit="mV",
            requires_sampling_rate=False,
            requires_lead=not data.leads_confident,
            requires_unit=False,
            warnings=list(data.warnings),
            n_samples=len(data.digital[0]),
            samples=[float(value) for value in preview],
        )

    # ----------------------------------------------------------------- parse
    def parse(self, source: ImportSource, parameters: ParseParameters) -> ParsedImport:
        data = self._analyze(source)
        source_unit = normalize_unit(parameters.unit) if parameters.unit else None
        if parameters.unit and source_unit is None:
            raise ImportApiError(
                "无法识别的单位参数（可用 mV/uV/nV/V）",
                code="invalid_parameter",
                details={"unit": parameters.unit},
            )
        if source_unit is not None:
            # 显式参数表示「每个 LSB 的原始单位」，覆盖 AVM。
            scale = unit_scale(source_unit) or (data.amplitude_multiplier_nv / 1_000_000.0)
        else:
            source_unit = "nV"
            scale = data.amplitude_multiplier_nv / 1_000_000.0

        leads: list[ParsedLead] = []
        for lead, values in zip(data.leads, data.digital):
            leads.append(
                ParsedLead(
                    lead=lead,
                    samples=values * scale,
                    digital=values,
                    gain=scale,
                )
            )

        parsed = ParsedImport(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            format=self.format,
            sampling_rate=data.sampling_rate,
            duration_sec=len(data.digital[0]) / data.sampling_rate,
            leads=leads,
            primary_lead=data.leads[0],
            source_unit=source_unit,
            metadata={
                "adapterId": self.adapter_id,
                "format": self.format,
                "sourceUnit": source_unit,
                "verification": "verified",
                "sectionIds": sorted(data.sections),
                "protocolVersion": data.protocol_version,
                "sectionVersion": data.section_version,
                "sampleIntervalUs": data.interval_us,
                "amplitudeMultiplierNv": data.amplitude_multiplier_nv,
                "encoding": data.encoding,
                "huffman": data.huffman,
                "leadCount": len(leads),
                "hasAnnotations": False,
                "annotationCount": 0,
            },
            warnings=list(data.warnings),
        )
        return finalize_parsed(parsed, parameters)


__all__ = ["ScpEcgImportAdapter"]

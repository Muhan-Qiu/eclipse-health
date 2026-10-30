"""合成 EDF / SCP-ECG 夹具（无真实样本时使用；标注为 synthetic）。"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

EDF_FIXED = 256
EDF_SIGNAL = 256


def _pad(text: str, width: int) -> bytes:
    raw = str(text).encode("latin-1", errors="replace")[:width]
    return raw + b" " * (width - len(raw))


def _digital_from_physical(
    samples: list[float] | np.ndarray,
    phys_min: float,
    phys_max: float,
    dig_min: float,
    dig_max: float,
) -> np.ndarray:
    values = np.asarray(samples, dtype=np.float64)
    slope = (phys_max - phys_min) / (dig_max - dig_min)
    digital = (values - phys_min) / slope + dig_min
    return np.clip(np.round(digital), dig_min, dig_max).astype(np.int16)


def build_edf(
    channels: list[dict[str, Any]],
    *,
    n_records: int = 1,
    record_duration: float = 1.0,
    startdate: str = "01.01.26",
    starttime: str = "10.00.00",
    declared_records: int | None = None,
    annotation_texts: list[str] | None = None,
) -> bytes:
    """每个 channel: label/dimension/phys_min/phys_max/dig_min/dig_max/samples。"""
    signals: list[dict[str, Any]] = []
    for channel in channels:
        samples = np.asarray(channel["samples"], dtype=np.float64)
        if samples.size % n_records:
            raise ValueError("样本数必须能被记录数整除")
        signals.append(
            {
                **channel,
                "digital": _digital_from_physical(
                    samples,
                    channel.get("phys_min", -5.0),
                    channel.get("phys_max", 5.0),
                    channel.get("dig_min", -32768),
                    channel.get("dig_max", 32767),
                ),
                "spr": samples.size // n_records,
            }
        )

    annotation_payload = b""
    if annotation_texts:
        chunks = [f"+0\x14\x14{text}\x14\x00".encode("latin-1") for text in annotation_texts]
        annotation_payload = b"".join(chunks)
        if len(annotation_payload) % 2:
            annotation_payload += b"\x00"
        spr = len(annotation_payload) // 2
        signals.append(
            {
                "label": "EDF Annotations",
                "dimension": "",
                "phys_min": 0.0,
                "phys_max": 1.0,
                "dig_min": -32768,
                "dig_max": 32767,
                "spr": spr,
                "digital": np.frombuffer(annotation_payload, dtype="<i2").astype(np.int16),
                "annotation": True,
            }
        )

    count = len(signals)
    header_bytes = EDF_FIXED + EDF_SIGNAL * count
    parts = [
        _pad("0", 8),
        _pad("X X X X", 80),
        _pad("Startdate X X X X", 80),
        _pad(startdate, 8),
        _pad(starttime, 8),
        _pad(str(header_bytes), 8),
        _pad("", 44),
        _pad(str(declared_records if declared_records is not None else n_records), 8),
        _pad(f"{record_duration:g}", 8),
        _pad(str(count), 4),
    ]
    header = b"".join(parts)
    assert len(header) == EDF_FIXED

    columns: list[list[bytes]] = [[] for _ in range(10)]
    widths = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
    for signal in signals:
        values = [
            str(signal.get("label", "")),
            str(signal.get("transducer", "")),
            str(signal.get("dimension", "")),
            f"{signal.get('phys_min', -5.0):g}",
            f"{signal.get('phys_max', 5.0):g}",
            f"{signal.get('dig_min', -32768):g}",
            f"{signal.get('dig_max', 32767):g}",
            str(signal.get("prefilter", "")),
            str(signal["spr"]),
            "",
        ]
        for column, value in enumerate(values):
            columns[column].append(_pad(value, widths[column]))
    header += b"".join(block for column in columns for block in column)

    data = bytearray()
    for record in range(n_records):
        for signal in signals:
            digital = signal["digital"]
            if signal.get("annotation"):
                block = digital
            else:
                start = record * signal["spr"]
                block = digital[start : start + signal["spr"]]
            data.extend(np.asarray(block, dtype="<i2").tobytes())
    return header + bytes(data)


def _section(section_id: int, body: bytes, *, version: int = 0x14) -> bytes:
    duration = len(body)
    size = 16 + duration
    header = struct.pack(
        "<HHIBB6s",
        0,
        section_id,
        size,
        version,
        version,
        b"\x00" * 6,
    )
    return header + body


def build_scp_ecg(
    leads: list[tuple[int, list[int]]],
    *,
    interval_us: int = 2000,
    amplitude_multiplier_nv: int = 1000,
    encoding: int = 0,
    huffman: bool = False,
    include_pointer: bool = True,
    include_header: bool = True,
    include_lead_section: bool = True,
    include_data_section: bool = True,
    custom_huffman: bool = False,
    compression: int = 0,
    flags: int = 0b100,
) -> bytes:
    """leads: (SCP 导联 ID, 样本列表)。按真实 EN 1064 段结构生成。"""
    lead_count = len(leads)
    if not leads or any(not samples for _, samples in leads):
        raise ValueError("每个导联至少需要一个样本")

    present: list[bytes] = []
    if include_header:
        present.append(_section(1, b""))
    if huffman or custom_huffman:
        marker = 12_345 if custom_huffman else 19_999
        present.append(_section(2, struct.pack("<H", marker)))

    if include_lead_section:
        lead_body = bytearray([lead_count, flags])
        for lead_id, samples in leads:
            lead_body.extend(struct.pack("<IIB", 1, len(samples), lead_id))
        present.append(_section(3, bytes(lead_body)))

    if include_data_section:
        data_body = bytearray()
        data_body.extend(
            struct.pack("<HHBB", amplitude_multiplier_nv, interval_us, encoding, compression)
        )
        raw_leads = [np.asarray(samples, dtype="<i2").tobytes() for _, samples in leads]
        for raw in raw_leads:
            data_body.extend(struct.pack("<H", len(raw)))
        for raw in raw_leads:
            data_body.extend(raw)
        present.append(_section(6, bytes(data_body)))

    # 指针段固定 12 项；先算各段绝对偏移（文件头 6 字节 + section 0 长度）。
    pointer_section_size = 16 + 12 * 10
    offsets: dict[int, tuple[int, int]] = {}
    cursor = 6 + (pointer_section_size if include_pointer else 0)
    for section in present:
        section_id = int.from_bytes(section[2:4], "little")
        offsets[section_id] = (len(section), cursor)
        cursor += len(section)

    pointer_body = bytearray()
    for section_id in range(12):
        length, index = offsets.get(section_id, (0, 0))
        pointer_body.extend(
            struct.pack("<HII", section_id, length, index + 1 if index else 0)
        )
    content = (_section(0, bytes(pointer_body)) if include_pointer else b"") + b"".join(
        present
    )
    return struct.pack("<HI", 0, 6 + len(content)) + content

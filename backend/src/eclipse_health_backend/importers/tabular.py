"""厂商文本导出（Apple / Samsung / Huawei）共用的表格读取。

只做最小的分隔符/表头/行读取与数值转换；列语义由各适配器决定。
编码顺序 UTF-8(BOM) → UTF-8 → GB18030 → Latin-1；``#`` 开头的行按注释保留，
因为厂商导出常把采样率写在注释里。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import warning
from .errors import invalid_file

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")
DELIMITERS = (",", ";", "\t", "|")
_UNIT_ANNOTATION_RE = re.compile(
    r"[\(\[]\s*(?:mv|uv|µv|μv|v|millivolt|microvolt|volt)\s*[\)\]]", re.IGNORECASE
)


@dataclass(slots=True)
class Table:
    header: list[str] | None
    rows: list[tuple[int, list[str]]]
    delimiter: str | None
    encoding: str
    comments: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def compact(text: str) -> str:
    """去掉单位标注与标点，便于列名匹配（保留中文）。"""
    cleaned = _UNIT_ANNOTATION_RE.sub(" ", str(text or "").lower())
    return re.sub(r"[^a-z0-9一-鿿]", "", cleaned)


def clean_field(token: str) -> str:
    return str(token).strip().strip('"').strip("'")


def is_number(token: str) -> bool:
    try:
        return math.isfinite(float(clean_field(token)))
    except (TypeError, ValueError):
        return False


def load_text(path: Path) -> tuple[str, str, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise invalid_file("无法读取文件", details={"reason": str(exc)}) from exc
    if b"\x00" in raw[:8192]:
        raise invalid_file("文件包含二进制内容，无法按文本表格解析")
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
    return text, encoding_used, warnings


def split_line(line: str, delimiter: str | None) -> list[str]:
    if delimiter is None:
        return [part for part in re.split(r"[ \t]+", line.strip()) if part]
    return [clean_field(part) for part in line.split(delimiter)]


def _sniff_delimiter(lines: list[str]) -> str | None:
    sample = [line for line in lines[:20] if line.strip()]
    best: tuple[tuple[int, int], str] | None = None
    for delimiter in DELIMITERS:
        counts = [len(split_line(line, delimiter)) for line in sample]
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


def parse_table(path: Path) -> Table:
    text, encoding, warnings = load_text(path)
    raw_lines = text.splitlines()
    comments = [line.strip()[1:].strip() for line in raw_lines if line.lstrip().startswith("#")]
    numbered = [
        (index + 1, line.strip())
        for index, line in enumerate(raw_lines)
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.lstrip().lower().startswith("sep=")
    ]
    if not numbered:
        raise invalid_file("文件里没有可解析的数据行")

    delimiter = _sniff_delimiter([line for _, line in numbered])

    # 第一条含数值的行视为数据起点；同列数的上一条「无任何数值」的行才是表头。
    # 时间列可以是 ISO 时间戳，因此不要求整行都是数字。
    start = None
    header: list[str] | None = None
    for index, (_line_number, line) in enumerate(numbered):
        fields = split_line(line, delimiter)
        if not fields or not any(is_number(token) for token in fields):
            continue
        start = index
        for back in range(index - 1, -1, -1):
            previous = split_line(numbered[back][1], delimiter)
            if len(previous) == len(fields) and not any(
                is_number(token) for token in previous
            ):
                header = previous
                break
            if len(fields) == 1 and not is_number(numbered[back][1]):
                # 单列且没有分隔符时，表头里的空格属于列名，不能按空白切分。
                header = [numbered[back][1].strip()]
                break
            if len(previous) == len(fields):
                break
        break
    if start is None:
        raise invalid_file("文件里找不到带数值的数据行")

    expected = len(header) if header is not None else len(split_line(numbered[start][1], delimiter))
    rows: list[tuple[int, list[str]]] = []
    for line_number, line in numbered[start:]:
        fields = split_line(line, delimiter)
        while fields and fields[-1] == "":
            fields.pop()
        if len(fields) != expected:
            raise invalid_file(
                "表格行的列数不一致",
                details={
                    "row": line_number,
                    "expectedColumns": expected,
                    "actualColumns": len(fields),
                },
            )
        rows.append((line_number, fields))

    return Table(
        header=header,
        rows=rows,
        delimiter=delimiter,
        encoding=encoding,
        comments=comments,
        warnings=warnings,
    )


def numeric_column(
    rows: list[tuple[int, list[str]]], column: int
) -> tuple[list[float], list[dict[str, Any]]]:
    """读取一列数值；坏单元格返回行号，不静默跳过。"""
    values: list[float] = []
    for line_number, fields in rows:
        token = fields[column]
        try:
            value = float(clean_field(token))
        except ValueError:
            raise invalid_file(
                "单元格不是数字",
                details={"row": line_number, "column": column + 1, "value": token[:64]},
            ) from None
        if not math.isfinite(value):
            raise invalid_file(
                "单元格不是有限数值",
                details={"row": line_number, "column": column + 1, "value": token[:64]},
            )
        values.append(value)
    return values, []


__all__ = [
    "Table",
    "clean_field",
    "compact",
    "is_number",
    "load_text",
    "numeric_column",
    "parse_table",
    "split_line",
]

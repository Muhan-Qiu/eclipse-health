"""Agent 沙箱内的解析 helper（``import eh_import_helpers``）。

只依赖 Python 标准库 + 可选 pypdf / openpyxl。所有路径都被限制在本次 session 的
``input/``、``work/``、``output/`` 内。

这些函数只负责“把文件读成结构化数据”，不做健康语义判断；语义与证据由 Agent
脚本决定，最终由服务端 ``propose_records`` 重新校验。
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

INPUT_DIR = Path(os.environ.get("EH_IMPORT_INPUT") or ".").resolve()
WORK_DIR = Path(os.environ.get("EH_IMPORT_WORK") or ".").resolve()
OUTPUT_DIR = Path(os.environ.get("EH_IMPORT_OUTPUT") or ".").resolve()

MAX_TEXT_BYTES = 1024 * 1024
MAX_CSV_ROWS = 100_000
MAX_TABLE_ROWS = 10_000
MAX_TABLES = 100
MAX_PDF_PAGES = 200
MAX_PDF_CHARS = 1_000_000
MAX_XLSX_ROWS = 100_000
MAX_ZIP_FILES = 500
MAX_ZIP_BYTES = 300 * 1024 * 1024


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #


def _resolve(root: Path, name: str) -> Path:
    raw = str(name or "")
    if not raw or "\\" in raw or ":" in raw or "\x00" in raw:
        raise ValueError(f"unsafe path: {name!r}")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"path escapes {root.name}: {name!r}")
    target = (root / Path(*candidate.parts)).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path escapes {root.name}: {name!r}")
    return target


def input_path(name: str) -> Path:
    path = _resolve(INPUT_DIR, name)
    if not path.is_file():
        raise FileNotFoundError(f"input file not found: {name}")
    return path


def work_path(name: str) -> Path:
    return _resolve(WORK_DIR, name)


def output_path(name: str) -> Path:
    return _resolve(OUTPUT_DIR, name)


def list_input_files() -> list[dict[str, object]]:
    items = []
    for path in sorted(INPUT_DIR.rglob("*")):
        if path.is_file() and not path.is_symlink():
            items.append(
                {
                    "name": path.relative_to(INPUT_DIR).as_posix(),
                    "size": path.stat().st_size,
                }
            )
    return items


# --------------------------------------------------------------------------- #
# 文本 / 编码
# --------------------------------------------------------------------------- #


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[: 64 * 1024]
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        sample.decode("gb18030")
        return "gb18030"
    except UnicodeDecodeError:
        return "latin-1"


def read_text(name: str, *, offset: int = 0, limit: int = MAX_TEXT_BYTES, encoding: str | None = None) -> str:
    path = input_path(name)
    encoding = encoding or detect_encoding(path)
    with path.open("rb") as handle:
        handle.seek(max(0, int(offset)))
        data = handle.read(max(1, min(int(limit), MAX_TEXT_BYTES)))
    return data.decode(encoding, errors="replace")


def _open_text(path: Path) -> io.TextIOBase:
    return path.open("r", encoding=detect_encoding(path), errors="replace", newline="")


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #


def read_csv_rows(
    name: str,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    max_rows: int = MAX_CSV_ROWS,
) -> dict[str, object]:
    """返回 ``{headers, rows, truncated}``；短行用空串补齐，重复表头自动加后缀。"""
    path = input_path(name)
    encoding = encoding or detect_encoding(path)
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        separator = delimiter
        if separator is None:
            try:
                separator = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                separator = ","
        reader = csv.reader(handle, delimiter=separator)
        headers: list[str] = []
        rows: list[dict[str, object]] = []
        truncated = False
        for index, raw in enumerate(reader):
            if index == 0:
                headers = _dedupe_headers(raw)
                continue
            if not any(str(cell).strip() for cell in raw):
                continue
            if len(rows) >= max_rows:
                truncated = True
                break
            padded = list(raw) + [""] * max(0, len(headers) - len(raw))
            rows.append(dict(zip(headers, padded, strict=False)))
    return {"headers": headers, "rows": rows, "truncated": truncated, "delimiter": separator}


def _dedupe_headers(raw: list[str]) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, cell in enumerate(raw):
        name = str(cell).strip() or f"column_{index + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count + 1}"
        headers.append(name)
    return headers


# --------------------------------------------------------------------------- #
# JSON / XML
# --------------------------------------------------------------------------- #


def read_json(name: str) -> object:
    path = input_path(name)
    return json.loads(path.read_text(encoding=detect_encoding(path), errors="replace"))


def read_xml(name: str) -> ElementTree.Element:
    """解析整份 XML；大文件请用 ``iter_xml`` 流式读取。"""
    path = input_path(name)
    return ElementTree.parse(str(path)).getroot()


def iter_xml(
    name: str, tag: str, *, max_items: int = 100_000
) -> list[ElementTree.Element]:
    """流式返回本地名等于 ``tag`` 的元素（忽略命名空间前缀）。"""
    path = input_path(name)
    items: list[ElementTree.Element] = []
    for _event, element in ElementTree.iterparse(str(path), events=("end",)):
        local = element.tag.rsplit("}", 1)[-1]
        if local == tag:
            items.append(element)
            if len(items) >= max_items:
                break
    return items


def xml_to_dict(element: ElementTree.Element, *, max_depth: int = 8) -> dict[str, object]:
    """把元素转成 ``{tag, attrs, text, children}``；用于少量元素。"""
    if max_depth <= 0:
        return {"tag": element.tag, "truncated": True}
    return {
        "tag": element.tag,
        "attrs": dict(element.attrib),
        "text": (element.text or "").strip()[:1000],
        "children": [xml_to_dict(child, max_depth=max_depth - 1) for child in list(element)[:200]],
    }


# --------------------------------------------------------------------------- #
# HTML 表格
# --------------------------------------------------------------------------- #


class _TableParser:
    def __init__(self) -> None:
        from html.parser import HTMLParser

        class Parser(HTMLParser):
            def __init__(inner) -> None:
                super().__init__(convert_charrefs=True)
                inner.tables: list[list[list[str]]] = []
                inner._table: list[list[str]] | None = None
                inner._row: list[str] | None = None
                inner._cell: list[str] | None = None

            def handle_starttag(inner, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
                if tag == "table" and inner._table is None:
                    inner._table = []
                elif tag == "tr" and inner._table is not None:
                    inner._row = []
                elif tag in {"td", "th"} and inner._row is not None:
                    inner._cell = []

            def handle_data(inner, data: str) -> None:
                if inner._cell is not None:
                    inner._cell.append(data)

            def handle_endtag(inner, tag: str) -> None:
                if tag in {"td", "th"} and inner._cell is not None:
                    assert inner._row is not None
                    inner._row.append("".join(inner._cell).strip())
                    inner._cell = None
                elif tag == "tr" and inner._row is not None and inner._table is not None:
                    if inner._row:
                        inner._table.append(inner._row)
                    inner._row = None
                elif tag == "table" and inner._table is not None:
                    inner.tables.append(inner._table)
                    inner._table = None

        self._parser = Parser()

    def parse(self, text: str) -> list[list[list[str]]]:
        self._parser.feed(text)
        self._parser.close()
        return self._parser.tables


def read_html_tables(
    name: str, *, max_tables: int = MAX_TABLES, max_rows: int = MAX_TABLE_ROWS
) -> list[dict[str, object]]:
    path = input_path(name)
    parser = _TableParser().parse(path.read_text(encoding=detect_encoding(path), errors="replace"))
    result: list[dict[str, object]] = []
    for table in parser[:max_tables]:
        rows = table[:max_rows]
        headers = _dedupe_headers(rows[0]) if rows else []
        body = [dict(zip(headers, row + [""] * max(0, len(headers) - len(row)), strict=False))
                for row in rows[1:]]
        result.append(
            {
                "headers": headers,
                "rows": body,
                "truncated": len(table) > len(rows),
            }
        )
    return result


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #


def read_xlsx_rows(
    name: str, *, sheet: str | None = None, max_rows: int = MAX_XLSX_ROWS
) -> dict[str, object]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - 依赖随核心打包
        raise RuntimeError("openpyxl is not available in this build") from exc

    path = input_path(name)
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[dict[str, object]] = []
    truncated = False
    try:
        names = [sheet] if sheet else list(workbook.sheetnames)
        for sheet_name in names:
            if sheet_name not in workbook.sheetnames:
                raise KeyError(f"sheet not found: {sheet_name}")
            worksheet = workbook[sheet_name]
            headers: list[str] = []
            rows: list[dict[str, object]] = []
            for index, raw in enumerate(worksheet.iter_rows(values_only=True)):
                values = ["" if cell is None else cell for cell in raw]
                if index == 0:
                    headers = _dedupe_headers([str(cell) for cell in values])
                    continue
                if not any(str(cell).strip() for cell in values):
                    continue
                if len(rows) >= max_rows:
                    truncated = True
                    break
                rows.append(dict(zip(headers, values, strict=False)))
            sheets.append({"name": sheet_name, "headers": headers, "rows": rows})
    finally:
        workbook.close()
    return {"sheets": sheets, "truncated": truncated}


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #


def read_pdf_pages(
    name: str, *, max_pages: int = MAX_PDF_PAGES, max_chars: int = MAX_PDF_CHARS
) -> dict[str, object]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 依赖随核心打包
        raise RuntimeError("pypdf is not available in this build") from exc

    path = input_path(name)
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise RuntimeError("PDF is encrypted")
    pages: list[dict[str, object]] = []
    total = 0
    truncated = False
    for index, page in enumerate(reader.pages):
        if index >= max_pages:
            truncated = True
            break
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - 单页解析失败不影响其他页
            text = ""
        total += len(text)
        if total > max_chars:
            text = text[: max(0, len(text) - (total - max_chars))]
            truncated = True
        pages.append({"page": index + 1, "text": text})
        if truncated:
            break
    return {"pageCount": len(reader.pages), "pages": pages, "truncated": truncated}


def pdf_text(name: str, *, max_pages: int = MAX_PDF_PAGES) -> str:
    payload = read_pdf_pages(name, max_pages=max_pages)
    return "\n\n".join(str(item["text"]) for item in payload["pages"])


# --------------------------------------------------------------------------- #
# ZIP
# --------------------------------------------------------------------------- #


def extract_zip_safe(
    name: str,
    *,
    dest: str = "unzipped",
    max_files: int = MAX_ZIP_FILES,
    max_bytes: int = MAX_ZIP_BYTES,
) -> list[str]:
    source = input_path(name)
    root = work_path(dest)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    extracted: list[str] = []
    total = 0
    with zipfile.ZipFile(source) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > max_files:
            raise RuntimeError(f"zip contains more than {max_files} files")
        for info in infos:
            raw = info.filename
            if not raw or "\\" in raw or ":" in raw:
                raise RuntimeError(f"unsafe zip entry: {raw!r}")
            relative = PurePosixPath(raw)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"zip entry escapes: {raw!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError(f"zip entry is a symlink: {raw!r}")
            target = (resolved_root / Path(*relative.parts)).resolve()
            if not target.is_relative_to(resolved_root):
                raise RuntimeError(f"zip entry escapes: {raw!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as sink:
                while chunk := src.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("zip exceeds the extraction size limit")
                    sink.write(chunk)
            extracted.append(relative.as_posix())
    return extracted


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #


def write_output_text(name: str, content: str) -> str:
    target = output_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target.relative_to(OUTPUT_DIR).as_posix()


def write_output_json(name: str, payload: object) -> str:
    return write_output_text(name, json.dumps(payload, ensure_ascii=False, indent=2))


__all__ = [
    "INPUT_DIR",
    "OUTPUT_DIR",
    "WORK_DIR",
    "detect_encoding",
    "extract_zip_safe",
    "input_path",
    "iter_xml",
    "list_input_files",
    "output_path",
    "pdf_text",
    "read_csv_rows",
    "read_html_tables",
    "read_json",
    "read_pdf_pages",
    "read_text",
    "read_xlsx_rows",
    "read_xml",
    "work_path",
    "write_output_json",
    "write_output_text",
    "xml_to_dict",
]

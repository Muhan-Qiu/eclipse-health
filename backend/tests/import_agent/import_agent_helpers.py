"""导入 Agent 测试工具：SSE 解析、会话上传、脚本化适配器、合成样例。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

API = "/api/v1/import-agent"


def upload_session(client, files: dict[str, bytes | str], **extra) -> dict[str, Any]:
    payload = []
    for name, content in files.items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        payload.append(("files", (name, data, "application/octet-stream")))
    response = client.post(f"{API}/sessions", files=payload, data=extra)
    assert response.status_code == 201, response.text
    return response.json()


def parse_sse(lines: list[str]) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name: str | None = None
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].strip())
        elif line == "" and name is not None:
            events.append((name, json.loads("\n".join(data)) if data else {}))
            name = None
            data = []
    if name is not None:
        events.append((name, json.loads("\n".join(data)) if data else {}))
    return events


def stream_run(
    client, session_id: str, body: dict[str, Any] | None = None
) -> tuple[int, list[tuple[str, dict[str, Any]]]]:
    with client.stream("POST", f"{API}/sessions/{session_id}/run", json=body or {}) as response:
        status = response.status_code
        if status != 200:
            return status, []
        return status, parse_sse(list(response.iter_lines()))


def commit(client, session_id: str, body: dict[str, Any] | None = None):
    return client.post(f"{API}/sessions/{session_id}/commit", json=body or {})


class ScriptedParseAdapter:
    """模拟“读文件 → 跑脚本 → 从 stdout 取记录 → propose → finish”。

    第 1 轮写脚本；第 2 轮运行；第 3 轮把 stdout 的 JSON 数组作为候选提交；
    第 4 轮 finish。用来验证完整 SSE/工具/提交链路，不依赖真实模型。
    """

    def __init__(self, script: str, *, script_name: str = "parse.py") -> None:
        self.script = script
        self.script_name = script_name

    async def stream(self, messages, tools, cancel):
        rounds = sum(1 for message in messages if message.get("role") == "assistant")
        if rounds == 0:
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "call_write",
                        "name": "write_script",
                        "args": {"name": self.script_name, "code": self.script},
                    }
                ],
            }
            return
        if rounds == 1:
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "call_run",
                        "name": "run_python",
                        "args": {"script": f"scripts/{self.script_name}", "timeout": 30},
                    }
                ],
            }
            return
        if rounds == 2:
            records = self._records(messages)
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "call_propose",
                        "name": "propose_records",
                        "args": {"records": records},
                    }
                ],
            }
            return
        if rounds == 3:
            yield {"type": "token", "text": "解析完成。"}
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "call_finish",
                        "name": "finish",
                        "args": {"summary": f"提交 {len(self._records(messages))} 条记录"},
                    }
                ],
            }
            return
        yield {"type": "token", "text": "结束。"}

    @staticmethod
    def _records(messages) -> list[dict[str, Any]]:
        for message in reversed(messages):
            if message.get("role") != "tool" or message.get("name") != "run_python":
                continue
            try:
                payload = json.loads(message.get("content") or "{}")
            except ValueError:
                return []
            if payload.get("exitCode") != 0:
                return []
            text = str(payload.get("stdout") or "").strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except ValueError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []


CSV_PULSE = """Date,Time,Pulse (bpm),Note
2026-10-30,08:00,72,rest
2026-10-30,08:05,78,walk
"""

CSV_SCRIPT = """
import json
import eh_import_helpers as h

data = h.read_csv_rows("pulse.csv")
records = []
for index, row in enumerate(data["rows"], start=2):
    pulse = next((v for k, v in row.items() if "pulse" in k.lower() or "heart" in k.lower()), None)
    date = next((v for k, v in row.items() if "date" in k.lower()), "")
    time = next((v for k, v in row.items() if "time" in k.lower() and "date" not in k.lower()), "")
    if not pulse or not date:
        continue
    records.append({
        "kind": "heart-rate",
        "value": float(pulse),
        "unit": "bpm",
        "startAt": f"{date.strip()}T{(time or '00:00').strip()}:00+08:00",
        "source": {"kind": "app", "app": "Test Export"},
        "evidence": {"file": "pulse.csv", "line": index, "snippet": str(pulse)},
        "confidence": 0.95,
    })
print(json.dumps(records, ensure_ascii=False))
"""


HTML_REPORT = """<!doctype html>
<html><body>
<h1>Health Report</h1>
<table>
  <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
  <tr><td>Heart Rate</td><td>72</td><td>bpm</td></tr>
  <tr><td>Systolic</td><td>120</td><td>mmHg</td></tr>
  <tr><td>Diastolic</td><td>80</td><td>mmHg</td></tr>
</table>
</body></html>
"""

HTML_SCRIPT = """
import json
import eh_import_helpers as h

tables = h.read_html_tables("report.html")
rows = {row["Metric"].lower(): row for row in tables[0]["rows"]}
records = []
hr = rows.get("heart rate")
if hr:
    records.append({
        "kind": "heart-rate",
        "value": float(hr["Value"]),
        "unit": hr["Unit"],
        "startAt": "2026-10-30T09:00:00+08:00",
        "source": {"kind": "app", "app": "Clinic Portal"},
        "evidence": {"file": "report.html", "locator": "table 1 row 1", "snippet": "Heart Rate 72 bpm"},
        "confidence": 0.9,
    })
systolic, diastolic = rows.get("systolic"), rows.get("diastolic")
if systolic and diastolic:
    records.append({
        "kind": "blood-pressure",
        "value": {"systolic": float(systolic["Value"]), "diastolic": float(diastolic["Value"])},
        "unit": systolic["Unit"],
        "startAt": "2026-10-30T09:00:00+08:00",
        "source": {"kind": "app", "app": "Clinic Portal"},
        "evidence": {"file": "report.html", "locator": "table 1 rows 2-3", "snippet": "120/80 mmHg"},
        "confidence": 0.9,
    })
print(json.dumps(records, ensure_ascii=False))
"""

PDF_SCRIPT = """
import json
import re
import eh_import_helpers as h

text = "\\n".join(page["text"] for page in h.read_pdf_pages("report.pdf")["pages"])
records = []
hr = re.search(r"Heart Rate:\\s*(\\d+)", text)
if hr:
    records.append({
        "kind": "heart-rate",
        "value": float(hr.group(1)),
        "unit": "bpm",
        "startAt": "2026-10-30T10:00:00+08:00",
        "source": {"kind": "app", "app": "PDF Report"},
        "evidence": {"file": "report.pdf", "page": 1, "snippet": hr.group(0)},
        "confidence": 0.9,
    })
bp = re.search(r"Blood Pressure:\\s*(\\d+)/(\\d+)\\s*mmHg", text)
if bp:
    records.append({
        "kind": "blood-pressure",
        "value": {"systolic": float(bp.group(1)), "diastolic": float(bp.group(2))},
        "unit": "mmHg",
        "startAt": "2026-10-30T10:00:00+08:00",
        "source": {"kind": "app", "app": "PDF Report"},
        "evidence": {"file": "report.pdf", "page": 1, "snippet": bp.group(0)},
        "confidence": 0.85,
    })
print(json.dumps(records, ensure_ascii=False))
"""


def build_pdf(lines: list[str]) -> bytes:
    """生成一个最小、xref 正确的单页 PDF（Helvetica 12pt）。"""
    content_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            content_lines.append("0 -20 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    return bytes(out)


def list_records(client, record_type: str) -> list[dict[str, Any]]:
    response = client.get("/api/v1/records", params={"recordType": record_type, "limit": 500})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def record_types(client) -> dict[str, int]:
    response = client.get(
        "/api/v1/records", params={"recordTypePrefix": "org.eclipsehealth.", "limit": 500}
    )
    assert response.status_code == 200, response.text
    counts: dict[str, int] = {}
    for item in response.json()["items"]:
        counts[item["recordType"]] = counts.get(item["recordType"], 0) + 1
    return counts


__all__ = [
    "API",
    "CSV_PULSE",
    "CSV_SCRIPT",
    "HTML_REPORT",
    "HTML_SCRIPT",
    "PDF_SCRIPT",
    "Path",
    "ScriptedParseAdapter",
    "build_pdf",
    "commit",
    "list_records",
    "parse_sse",
    "record_types",
    "stream_run",
    "upload_session",
]

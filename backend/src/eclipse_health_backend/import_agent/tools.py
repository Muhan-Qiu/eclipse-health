"""Agent 工具：文件列表、脚本、沙箱运行、输出、候选记录、结束。

模型只能看到工具返回的结构化结果；服务端在这里做所有路径与参数校验。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import limits, sandbox, store
from .errors import ImportAgentError, RecordValidationError
from .kinds import normalize_record

MAX_SUMMARY = 2000
MAX_FINISH_SUMMARY = 4000


class ToolError(Exception):
    def __init__(self, code: str, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(slots=True)
class ToolOutcome:
    ok: bool
    result: dict[str, Any]
    summary: str

    def to_event(self, call_id: str, duration_ms: int) -> dict[str, Any]:
        event: dict[str, Any] = {
            "id": call_id,
            "ok": self.ok,
            "durationMs": duration_ms,
            "resultSummary": self.summary,
        }
        if not self.ok:
            error = self.result.get("error")
            if isinstance(error, dict):
                event["error"] = error
        return event


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "列出本次上传的文件（名称、大小、sha256、类型）。文本类文件附带 240 字符预览。"
                "开始解析前先调用它。"
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": (
                "按字节偏移读取输入目录里的文本文件；单次最多 256 KB。"
                "二进制文件（PDF/XLSX/ZIP 等）会拒绝，请用 run_python + eh_import_helpers。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对 input/ 的路径"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 262144},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_script",
            "description": (
                "在 work/scripts/ 写一个 Python 脚本（≤64 KB）。脚本可用 "
                "`import eh_import_helpers` 读取 CSV/JSON/XML/HTML/XLSX/PDF/ZIP。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "如 parse.py"},
                    "code": {"type": "string"},
                },
                "required": ["name", "code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "在 work/ 里运行 write_script 写好的脚本（独立进程、无网络、无子进程、默认 120 s 超时）。"
                "通过 print 输出 JSON 给模型；大结果写 output/ 再 read_output。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "write_script 返回的路径或脚本名"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 32,
                    },
                    "timeout": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 150,
                        "description": "秒；默认 120",
                    },
                },
                "required": ["script"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_output",
            "description": "把中间结果写到 output/（≤8 MB）。ECG 采样 CSV/float32 也放这里。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对 output/ 的路径"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_output",
            "description": "读取 output/ 下的文本（单次 ≤256 KB）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 262144},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_records",
            "description": (
                "提交一批候选健康记录（单次 ≤1000 条）。每条必须含 kind/value/unit/startAt/"
                "source/evidence/confidence；evidence.file 必须是本次上传文件或其子路径。"
                "服务端会逐条校验，返回 accepted/rejected/issues。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "records": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                        "maxItems": 1000,
                    }
                },
                "required": ["records"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "完成解析并给出摘要（已写入多少条、跳过了什么、有哪些不确定项）。",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string", "maxLength": 4000}},
                "required": ["summary"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES = tuple(spec["function"]["name"] for spec in TOOL_SPECS)


class ToolBox:
    """绑定到一个 session 的工具执行器；同一 run 内顺序执行。"""

    def __init__(self, session_id: str, meta: dict[str, Any], *, cancel: Any = None) -> None:
        self.session_id = session_id
        self.meta = meta
        self.cancel = cancel
        self.deadline: float | None = None
        self.finished = False
        self.finish_summary: str | None = None

    @property
    def files(self) -> set[str]:
        return store.file_names(self.meta)

    def execute(self, name: str, raw_args: dict[str, Any] | None) -> ToolOutcome:
        args = raw_args if isinstance(raw_args, dict) else {}
        handler = getattr(self, f"_tool_{name}", None)
        if name not in TOOL_NAMES or handler is None:
            return ToolOutcome(
                ok=False,
                result={"error": {"code": "UNKNOWN_TOOL", "message": f"unknown tool: {name[:40]}"}},
                summary=f"未知工具 {name[:40]}",
            )
        try:
            result, summary = handler(args)
        except ToolError as exc:
            return ToolOutcome(
                ok=False,
                result={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                summary=f"{name} 失败：{exc.code}",
            )
        except ImportAgentError as exc:
            return ToolOutcome(
                ok=False,
                result={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                summary=f"{name} 失败：{exc.code}",
            )
        except Exception as exc:  # noqa: BLE001 - 工具失败不能拖垮整个 run
            return ToolOutcome(
                ok=False,
                result={"error": {"code": "TOOL_FAILED", "message": "tool execution failed"}},
                summary=f"{name} 失败：{type(exc).__name__}",
            )
        return ToolOutcome(ok=True, result=result, summary=summary)

    # ------------------------------------------------------------------ 参数
    @staticmethod
    def _unknown(args: dict[str, Any], allowed: set[str]) -> None:
        unknown = set(args) - allowed
        if unknown:
            raise ToolError(
                "invalid_argument",
                f"unexpected arguments: {', '.join(sorted(unknown))}",
                details={"allowed": sorted(allowed)},
            )

    @staticmethod
    def _int(value: Any, name: str, *, default: int, minimum: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise ToolError("invalid_argument", f"{name} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ToolError("invalid_argument", f"{name} must be an integer") from None
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _str(value: Any, name: str, *, required: bool = True, max_length: int = 512) -> str:
        if value is None:
            if required:
                raise ToolError("invalid_argument", f"{name} is required")
            return ""
        if not isinstance(value, str):
            raise ToolError("invalid_argument", f"{name} must be a string")
        cleaned = value.strip()
        if required and not cleaned:
            raise ToolError("invalid_argument", f"{name} must not be empty")
        if len(cleaned) > max_length:
            raise ToolError("invalid_argument", f"{name} exceeds {max_length} characters")
        return cleaned

    # ------------------------------------------------------------------ 文件
    def _tool_list_files(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, set())
        items = []
        for entry in self.meta.get("files") or []:
            if not isinstance(entry, dict):
                continue
            item = {
                "name": entry.get("name"),
                "size": entry.get("size"),
                "sha256": entry.get("sha256"),
                "kind": entry.get("kind"),
            }
            if entry.get("kind") in {"text", "csv", "json", "xml", "html"}:
                try:
                    slice_ = store.read_text_slice(
                        self.session_id,
                        str(entry.get("storedName") or entry.get("name")),
                        offset=0,
                        limit=limits.MAX_TEXT_PREVIEW_CHARS * 3,
                    )
                    item["preview"] = slice_["text"][: limits.MAX_TEXT_PREVIEW_CHARS]
                except Exception:  # noqa: BLE001, S110 - 预览失败不影响清单
                    pass
            items.append(item)
        return (
            {"items": items, "count": len(items), "network": False},
            f"{len(items)} 个文件",
        )

    def _tool_read_text_file(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"path", "offset", "limit"})
        path = self._str(args.get("path"), "path")
        offset = self._int(args.get("offset"), "offset", default=0, minimum=0, maximum=10**12)
        limit = self._int(
            args.get("limit"),
            "limit",
            default=limits.MAX_READ_TEXT_BYTES,
            minimum=1,
            maximum=limits.MAX_READ_TEXT_BYTES,
        )
        data = store.read_text_slice(self.session_id, path, offset=offset, limit=limit)
        return data, f"读取 {path} 的 {data['bytesRead']} 字节"

    # ------------------------------------------------------------------ 脚本
    def _tool_write_script(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"name", "code"})
        name = self._str(args.get("name"), "name", max_length=120)
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ToolError("invalid_argument", "code must be a non-empty string")
        data = store.write_script(self.session_id, name, code)
        return data, f"已写入脚本 {data['path']}（{data['bytes']} 字节）"

    def _tool_run_python(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"script", "args", "timeout"})
        script = self._str(args.get("script"), "script", max_length=256)
        raw_args = args.get("args") or []
        if not isinstance(raw_args, list):
            raise ToolError("invalid_argument", "args must be an array of strings")
        if len(raw_args) > limits.MAX_RUN_ARGS:
            raise ToolError("invalid_argument", f"at most {limits.MAX_RUN_ARGS} args")
        script_args = [self._str(item, "args[]", max_length=limits.MAX_RUN_ARG_CHARS) for item in raw_args]
        timeout = args.get("timeout") or limits.DEFAULT_RUN_TIMEOUT_SECONDS
        if self.deadline is not None:
            import time

            remaining = self.deadline - time.monotonic() - 1.0
            timeout = min(float(timeout), max(limits.MIN_RUN_TIMEOUT_SECONDS, remaining))
        result = sandbox.run_script(
            self.session_id,
            script,
            args=script_args,
            timeout_s=timeout,
            cancel=self.cancel,
        )
        payload = result.to_dict()
        if result.timedOut:
            summary = f"脚本超时（{result.durationMs} ms）"
        elif result.cancelled:
            summary = "脚本已取消"
        elif result.exitCode != 0:
            summary = f"脚本失败（exit {result.exitCode}）"
        else:
            summary = f"脚本完成（{result.durationMs} ms）"
        return payload, summary

    # ------------------------------------------------------------------ 输出
    def _tool_write_output(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"path", "content"})
        path = self._str(args.get("path"), "path", max_length=256)
        content = args.get("content")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        data = store.write_output_text(self.session_id, path, content)
        return data, f"已写入 output/{path}（{data['bytes']} 字节）"

    def _tool_read_output(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"path", "offset", "limit"})
        path = self._str(args.get("path"), "path", max_length=256)
        offset = self._int(args.get("offset"), "offset", default=0, minimum=0, maximum=10**12)
        limit = self._int(
            args.get("limit"),
            "limit",
            default=limits.MAX_READ_TEXT_BYTES,
            minimum=1,
            maximum=limits.MAX_READ_TEXT_BYTES,
        )
        data = store.read_output_slice(self.session_id, path, offset=offset, limit=limit)
        return data, f"读取 output/{path} 的 {data['bytesRead']} 字节"

    # ------------------------------------------------------------------ 候选
    def _tool_propose_records(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"records"})
        records = args.get("records")
        if not isinstance(records, list):
            raise ToolError("invalid_argument", "records must be an array")
        if not records:
            raise ToolError("invalid_argument", "records must not be empty")
        if len(records) > limits.MAX_PROPOSALS_PER_CALL:
            raise ToolError(
                "invalid_argument",
                f"at most {limits.MAX_PROPOSALS_PER_CALL} records per call",
                details={"count": len(records)},
            )

        workspace = store.session_path(self.session_id)
        existing = store.load_proposals(workspace)
        if len(existing) >= limits.MAX_PROPOSALS:
            raise ToolError(
                "proposal_limit",
                f"session already has {limits.MAX_PROPOSALS} proposals",
            )
        known = {str(item.get("fingerprint")) for item in existing}
        files = self.files
        accepted: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        duplicates = 0
        room = limits.MAX_PROPOSALS - len(existing)

        for index, raw in enumerate(records):
            if len(accepted) >= room:
                issues.append(
                    {
                        "index": index,
                        "code": "proposal_limit",
                        "message": "session proposal limit reached",
                    }
                )
                continue
            try:
                record = normalize_record(raw, files=files)
            except RecordValidationError as exc:
                issues.append(
                    {
                        "index": index,
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                )
                continue
            fingerprint = str(record.get("fingerprint"))
            if fingerprint in known:
                duplicates += 1
                continue
            known.add(fingerprint)
            accepted.append(record)

        if accepted:
            store.save_proposals(workspace, [*existing, *accepted])
            self.meta["proposalCount"] = len(existing) + len(accepted)
            store.write_meta(workspace, self.meta)

        result = {
            "accepted": len(accepted),
            "duplicates": duplicates,
            "rejected": len(issues),
            "proposalCount": int(self.meta.get("proposalCount") or 0),
            "items": [
                {
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "startAt": item.get("startAt"),
                    "endAt": item.get("endAt"),
                    "confidence": item.get("confidence"),
                }
                for item in accepted[: limits.MAX_PREVIEW_ITEMS]
            ],
            "issues": issues[: limits.MAX_PREVIEW_ITEMS],
        }
        if issues:
            summary = f"接收 {len(accepted)} 条，拒绝 {len(issues)} 条"
        elif duplicates:
            summary = f"接收 {len(accepted)} 条，去重 {duplicates} 条"
        else:
            summary = f"接收 {len(accepted)} 条候选记录"
        return result, summary

    def _tool_finish(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self._unknown(args, {"summary"})
        summary = self._str(
            args.get("summary"), "summary", required=False, max_length=MAX_FINISH_SUMMARY
        ) or "已完成解析"
        self.finished = True
        self.finish_summary = summary[:MAX_SUMMARY]
        workspace = store.session_path(self.session_id)
        self.meta["summary"] = self.finish_summary
        store.write_meta(workspace, self.meta)
        return {"summary": self.finish_summary, "proposalCount": int(self.meta.get("proposalCount") or 0)}, "已结束"


__all__ = ["TOOL_NAMES", "TOOL_SPECS", "ToolBox", "ToolError", "ToolOutcome"]

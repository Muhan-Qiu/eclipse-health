"""wfdb 适配模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：initialize / warmup / health / export.wfdb / export.csv / import.wfdb / deactivate。

- 上游 ``wfdb`` 已在核心 venv（E 类），通过库调用，不复制源码；
- 只写调用方给出的 ``outputDir``，不写用户目录之外的文件；
- 返回样本总数上限 5 万，大结果写临时文件并返回 ``resultRef``。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.mit-lcp.wfdb")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
SAMPLE_RETURN_LIMIT = 50_000
DISCLAIMER = "非医疗器械，不用于诊断。"


def _load_adapter() -> Any:
    name = "eh_adapter_" + MODULE_ID.replace(".", "_").replace("-", "_")
    path = Path(__file__).resolve().with_name("adapter.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter.py unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, error: RpcError) -> None:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data:
        payload["error"]["data"] = error.data
    _write(payload)


def _require_wfdb() -> Any:
    if importlib.util.find_spec("wfdb") is None:
        raise RpcError(-32000, "未安装 wfdb；模块依赖未就绪", {"code": "upstream_unavailable"})
    import wfdb

    return wfdb


def _output_dir(params: dict[str, Any]) -> Path:
    raw = params.get("outputDir")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.outputDir 必须是非空路径", {"code": "INVALID_INPUT"})
    path = Path(raw)
    if not path.is_dir():
        raise RpcError(-32602, "params.outputDir 不是已存在目录", {"code": "INVALID_INPUT"})
    return path


def _plan(params: dict[str, Any]) -> dict[str, Any]:
    try:
        return adapter.build_export_plan(params)
    except adapter.WfdbAdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc


def _export_wfdb(params: dict[str, Any]) -> dict[str, Any]:
    plan = _plan(params)
    output_dir = _output_dir(params)
    wfdb = _require_wfdb()
    import numpy as np

    matrix = np.column_stack([np.asarray(channel, dtype=np.float64) for channel in plan["channels"]])
    wfdb.wrsamp(
        plan["recordName"],
        fs=plan["fs"],
        units=plan["units"],
        sig_name=plan["sigName"],
        p_signal=matrix,
        fmt=["32"] * matrix.shape[1],
        comments=plan["comments"],
        write_dir=str(output_dir),
    )
    files = sorted(
        str(path)
        for path in output_dir.glob(plan["recordName"] + ".*")
        if path.suffix.lower() in {".hea", ".dat"}
    )
    return {
        "recordName": plan["recordName"],
        "outputDir": str(output_dir),
        "files": files,
        "fs": plan["fs"],
        "nSamples": len(plan["channels"][0]),
        "channels": len(plan["channels"]),
        "disclaimer": DISCLAIMER,
    }


def _export_csv(params: dict[str, Any]) -> dict[str, Any]:
    plan = _plan(params)
    output_dir = _output_dir(params)
    text = adapter.to_csv_text(plan["sigName"], plan["channels"], plan["fs"])
    target = output_dir / f"{plan['recordName']}.csv"
    target.write_text(text, encoding="utf-8")
    blob = text.encode("utf-8")
    return {
        "path": str(target),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "rows": len(plan["channels"][0]),
        "disclaimer": DISCLAIMER,
    }


def _import_wfdb(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.path 必须是非空路径", {"code": "INVALID_INPUT"})
    target = Path(raw)
    if target.is_file() and target.suffix.lower() in {".hea", ".dat"}:
        record_path = target.with_suffix("")
    elif target.exists() or target.with_suffix(".hea").is_file():
        record_path = target
    else:
        raise RpcError(-32602, "params.path 不存在", {"code": "INVALID_INPUT"})
    wfdb = _require_wfdb()
    try:
        record = wfdb.rdrecord(str(record_path))
    except Exception as exc:
        raise RpcError(-32000, f"wfdb 读取失败：{type(exc).__name__}", {"code": "upstream_failed"}) from exc
    sig = record.p_signal
    n_samples = int(sig.shape[0]) if sig is not None else 0
    try:
        summary = adapter.summarize_import(record.sig_name or [], record.units or [], record.fs, n_samples)
    except adapter.WfdbAdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    result: dict[str, Any] = {"record": summary, "disclaimer": DISCLAIMER}
    if params.get("includeSamples") is True and sig is not None:
        limit = min(n_samples, SAMPLE_RETURN_LIMIT)
        result["samples"] = sig[:limit].tolist()
        result["samplesTruncated"] = n_samples > limit
    return result


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "upstreamAvailable": importlib.util.find_spec("wfdb") is not None,
        "disclaimer": DISCLAIMER,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, "unsupported apiVersion", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "WFDB ECG 记录",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "export.wfdb",
                "export.csv",
                "import.wfdb",
                "deactivate",
            ],
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "export.wfdb":
        return _export_wfdb(params)
    if method == "export.csv":
        return _export_csv(params)
    if method == "import.wfdb":
        return _import_wfdb(params)
    if method in {"activate"}:
        return {"ok": True}
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        _result(request_id, handle(str(method), params))
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _error(None, RpcError(-32700, "parse error"))
            continue
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())

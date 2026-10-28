"""错误码与异常：与 MODULE_CONTRACT_V1 §12 对齐，模块内核内部再补充少量扩展码。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 契约 §12 标准码 + 内核扩展码（扩展码以 EXT_ 前缀常量区分，API 中同样以字符串返回）。
# HTTP 状态只决定 REST 语义，RPC 层使用 JSON-RPC error.data.code 传递同名错误码。
_ERROR_SPECS: dict[str, tuple[int, str]] = {
    # 契约 §12
    "MODULE_CRASH": (502, "模块进程崩溃"),
    "MODULE_TIMEOUT": (504, "模块调用超时"),
    "PERMISSION_DENIED": (403, "权限不足"),
    "INVALID_INPUT": (422, "输入不符合 schema"),
    "INCOMPATIBLE_API": (409, "模块契约版本不兼容"),
    "MODEL_LOAD_FAILED": (502, "模型加载或校验失败"),
    "RESOURCE_EXCEEDED": (507, "超出资源上限"),
    "CANCELLED": (409, "操作已取消"),
    # 内核扩展（不属于 §12，但 API 必须能表达这些失败）
    "MODULE_NOT_FOUND": (404, "模块未安装"),
    "MODULE_ALREADY_INSTALLED": (409, "模块版本已安装"),
    "MODULE_DISABLED": (409, "模块未启用"),
    "INVALID_PACKAGE": (422, "模块包格式无效"),
    "CHECKSUM_MISMATCH": (422, "文件校验和不匹配"),
    "UNSAFE_PACKAGE_PATH": (422, "模块包包含不安全路径"),
    "MODULE_ERROR": (502, "模块返回错误"),
    "METHOD_NOT_FOUND": (404, "方法不存在"),
    "NOT_IMPLEMENTED": (501, "功能尚未实现"),
}

_RPC_APP_CODE_BASE = -32000
_RPC_CODES: dict[str, int] = {
    "PERMISSION_DENIED": -32001,
    "MODULE_TIMEOUT": -32002,
    "MODULE_CRASH": -32003,
    "INCOMPATIBLE_API": -32004,
    "RESOURCE_EXCEEDED": -32005,
    "CANCELLED": -32006,
    "MODULE_ERROR": -32007,
    "NOT_IMPLEMENTED": -32008,
    "MODULE_NOT_FOUND": -32009,
    "MODULE_DISABLED": -32010,
    "METHOD_NOT_FOUND": -32601,
    "INVALID_INPUT": -32602,
}
_RPC_CODE_TO_NAME = {v: k for k, v in _RPC_CODES.items()}
_RPC_CODE_TO_NAME[-32600] = "INVALID_INPUT"
_RPC_CODE_TO_NAME[-32603] = "MODULE_ERROR"


@dataclass(slots=True)
class ModuleError(Exception):
    """带契约错误码的业务异常。message 不得包含绝对路径或健康数据。"""

    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in _ERROR_SPECS:
            raise ValueError(f"unknown module error code: {self.code}")
        # slots=True 会重建 dataclass，零参 super() 在此失效，显式调用。
        Exception.__init__(self, self.message)

    @property
    def http_status(self) -> int:
        return _ERROR_SPECS[self.code][0]

    def to_http_detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload

    def to_rpc_error(self) -> dict[str, Any]:
        return {
            "code": _RPC_CODES.get(self.code, _RPC_APP_CODE_BASE),
            "message": self.message,
            "data": {"code": self.code, **({"detail": self.detail} if self.detail else {})},
        }


def code_from_rpc_error(error: dict[str, Any] | None, fallback: str = "MODULE_ERROR") -> str:
    """把模块返回的 JSON-RPC error 还原为契约错误码，未知时退回 fallback。"""
    data = (error or {}).get("data")
    if isinstance(data, dict):
        code = data.get("code")
        if isinstance(code, str) and code in _ERROR_SPECS:
            return code
    rpc_code = (error or {}).get("code")
    if isinstance(rpc_code, int):
        return _RPC_CODE_TO_NAME.get(rpc_code, fallback)
    return fallback


def rpc_error_from_exception(exc: ModuleError) -> dict[str, Any]:
    return exc.to_rpc_error()


def is_known_error_code(code: str) -> bool:
    return code in _ERROR_SPECS

"""市场模块的业务错误。

与模块内核的 ``ModuleError`` 分开：市场错误发生在下载/验签阶段，
错误码不属于模块契约 §12，但 REST 响应体保持同样的 ``{code, message, details}`` 形状。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# code -> (HTTP status, default message)
_ERROR_SPECS: dict[str, tuple[int, str]] = {
    "marketplace_not_configured": (503, "市场源未配置"),
    "marketplace_source_invalid": (422, "市场源只能是 official 或 community"),
    "marketplace_fetch_failed": (502, "无法读取市场索引"),
    "marketplace_index_invalid": (502, "市场索引格式无效"),
    "marketplace_signature_invalid": (502, "市场索引签名无效"),
    "marketplace_module_not_found": (404, "索引中没有该模块版本"),
    "marketplace_download_failed": (502, "模块包下载失败"),
    "marketplace_download_url_rejected": (400, "拒绝从该地址下载模块包"),
    "marketplace_checksum_mismatch": (422, "模块包大小或 sha256 与索引不一致"),
    "marketplace_resource_exceeded": (413, "模块包或索引超过大小上限"),
    "marketplace_incompatible_core": (409, "模块要求更高版本的核心"),
}

SOURCES = ("official", "community")


@dataclass(slots=True)
class MarketplaceError(Exception):
    """带错误码的市场异常；message 不包含本机绝对路径或健康数据。"""

    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in _ERROR_SPECS:
            raise ValueError(f"unknown marketplace error code: {self.code}")
        Exception.__init__(self, self.message)

    @property
    def http_status(self) -> int:
        return _ERROR_SPECS[self.code][0]

    def to_http_detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            payload["details"] = self.detail
        return payload


def validate_source(source: str) -> str:
    if source not in SOURCES:
        raise MarketplaceError(
            "marketplace_source_invalid",
            "source 只能是 official 或 community",
            {"allowed": list(SOURCES)},
        )
    return source

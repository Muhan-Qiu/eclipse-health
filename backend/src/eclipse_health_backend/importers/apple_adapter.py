"""Apple Health 心电图 CSV 适配器。

Apple 的 Health 导出里，心电图是单导联 I、单位为 mV 的 CSV；
文件名通常含 ``electrocardiogram``，也可能被用户重命名。因此除了文件名，
还识别「time + voltage/Lead I」表头签名；只有这种签名才接管 CSV，
避免把普通单导联 CSV 误判成 Apple。
"""

from __future__ import annotations

from pathlib import Path

from .base import LEAD_ALIASES
from .errors import ImportApiError
from .tabular import compact, parse_table
from .vendor_adapter import (
    TEXT_SUFFIXES,
    VendorImportAdapter,
    VendorProfile,
    _is_time_token,
)

APPLE_PROFILE = VendorProfile(
    adapter_id="org.eclipsehealth.apple",
    format="apple",
    label="Apple Health",
    brand="Apple",
    name_tokens=("electrocardiogram", "appleecg", "applehealth", "apple"),
    default_lead="I",
    infer_voltage_unit=True,
)


class AppleImportAdapter(VendorImportAdapter):
    profile = APPLE_PROFILE

    def _content_marked(self, path: Path) -> bool:
        return super()._content_marked(path) or self._apple_signature(path)

    @staticmethod
    def _apple_signature(path: Path) -> bool:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            return False
        try:
            table = parse_table(path)
        except ImportApiError:
            return False
        if not table.header:
            return False
        tokens = [compact(name) for name in table.header]
        has_time = any(_is_time_token(token) for token in tokens)
        # 只把明确写 Lead I 的列当作 Apple 内容签名；普通 "time,voltage"
        # 仍交给通用 CSV，避免把三星/华为或未知来源误标成 Apple。
        apple_voltage = any(token in {"leadi", "lead1", "leadone"} for token in tokens)
        standard_lead = any(
            token in LEAD_ALIASES and token not in {"ecg", "ekg"}
            for token in tokens
        )
        return has_time and apple_voltage and not standard_lead

"""Samsung Health 导出适配器（CSV / JSON）。

Samsung Health 没有统一的公开原始波形导出格式；这里只映射公开资料里常见的
``time / voltage / samplingRate / unit / lead`` 字段。没有真实样本验证，
因此格式标记为 ``experimental``，缺失字段一律用 ``requires`` 让用户补齐。
"""

from __future__ import annotations

from .vendor_adapter import VendorImportAdapter, VendorProfile

SAMSUNG_PROFILE = VendorProfile(
    adapter_id="org.eclipsehealth.samsung",
    format="samsung",
    label="Samsung Health",
    brand="Samsung",
    name_tokens=("samsung", "galaxy", "samsunghealth"),
)


class SamsungImportAdapter(VendorImportAdapter):
    profile = SAMSUNG_PROFILE

"""华为运动健康导出适配器（CSV / JSON）。

公开资料最少，字段按常见的 ``samples / samplingRate / unit / lead`` 映射；
没有真实样本验证，缺失采样率/单位/导联时强制用户确认，不编造字段。
"""

from __future__ import annotations

from .vendor_adapter import VendorImportAdapter, VendorProfile

HUAWEI_PROFILE = VendorProfile(
    adapter_id="org.eclipsehealth.huawei",
    format="huawei",
    label="华为运动健康",
    brand="Huawei",
    name_tokens=("huawei", "华为", "watchd", "huaweiecg"),
)


class HuaweiImportAdapter(VendorImportAdapter):
    profile = HUAWEI_PROFILE

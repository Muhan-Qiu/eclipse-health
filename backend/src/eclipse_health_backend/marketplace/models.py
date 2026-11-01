"""市场索引的 Pydantic 模型。

字段名使用 camelCase 与 ``prompts/130-marketplace-backend.md`` 的索引格式一致；
Python 侧使用 snake_case，API 输出时统一 ``by_alias=True``。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MarketplaceEntry(BaseModel):
    """索引里的一个模块版本。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    name: str
    version: str
    type: str
    description: str = ""
    author: str = ""
    license: str = ""
    repository: str = ""
    permissions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    min_core_version: str = Field(default="0.1.0", alias="minCoreVersion")
    categories: list[str] = Field(default_factory=list)
    verified: bool = True
    file: str
    size: int
    sha256: str


class MarketplaceIndex(BaseModel):
    """签名后的完整索引；``signature`` 不参与自身签名。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    schema_version: str = Field(default="1", alias="schemaVersion")
    source: str
    generated_at: str = Field(alias="generatedAt")
    key_id: str = Field(alias="keyId")
    modules: list[MarketplaceEntry] = Field(default_factory=list)
    signature: str = ""


class MarketplaceInstallResult(BaseModel):
    """安装响应：索引来源信息 + 内核返回的模块摘要。"""

    source: str
    moduleId: str
    version: str
    keyId: str
    verified: bool
    sha256: str
    size: int
    module: dict[str, object]


class MarketplaceUpdate(BaseModel):
    moduleId: str
    name: str
    installedVersion: str
    latestVersion: str
    source: str
    verified: bool
    size: int
    sha256: str
    file: str

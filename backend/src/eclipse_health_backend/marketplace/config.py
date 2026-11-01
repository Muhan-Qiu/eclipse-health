"""市场源配置：环境变量优先，未设置时回退到仓库内的开发索引。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..settings import BACKEND_ROOT

PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_PUBLIC_KEY = Path(__file__).resolve().parent / "public_key.txt"

OFFICIAL_ENV = "EH_MARKETPLACE_OFFICIAL_URL"
COMMUNITY_ENV = "EH_MARKETPLACE_COMMUNITY_URL"
PUBLIC_KEY_ENV = "EH_MARKETPLACE_PUBLIC_KEY"


def _default_index_url(source: str) -> str:
    # 打包后索引随 sidecar 放在包内；开发时回退到仓库 marketplace/。
    package_index = (
        Path(__file__).resolve().parent / "indexes" / source / "index.json"
    )
    if package_index.is_file():
        return package_index.as_uri()
    return (PROJECT_ROOT / "marketplace" / source / "index.json").as_uri()


@dataclass(frozen=True, slots=True)
class MarketplaceConfig:
    """一条市场源配置；空字符串表示显式关闭该源。"""

    official_url: str | None
    community_url: str | None
    public_key_path: Path

    @classmethod
    def from_env(cls) -> MarketplaceConfig:
        official = os.environ.get(OFFICIAL_ENV, _default_index_url("official")).strip()
        community = os.environ.get(COMMUNITY_ENV, _default_index_url("community")).strip()
        key = os.environ.get(PUBLIC_KEY_ENV, "").strip()
        return cls(
            official_url=official or None,
            community_url=community or None,
            public_key_path=Path(key) if key else DEFAULT_PUBLIC_KEY,
        )

    def url_for(self, source: str) -> str | None:
        return self.official_url if source == "official" else self.community_url

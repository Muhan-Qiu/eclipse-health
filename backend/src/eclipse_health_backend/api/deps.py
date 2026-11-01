"""API 依赖别名，避免在每个路由里重复书写 ``Depends``。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from ..db.base import get_session

SessionDep = Annotated[Session, Depends(get_session)]

__all__ = ["SessionDep"]

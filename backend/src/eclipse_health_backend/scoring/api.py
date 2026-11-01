"""评分与建议 API（G2）。

路径为 ``/scores`` 与 ``/suggestions``，由指挥官在 ``api/__init__.py`` 统一挂载到
``/api/v1``；本模块不直接修改路由汇总文件。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..api.deps import SessionDep
from .models import ScoreReport, SuggestionList
from .service import build_score_report
from .suggestions import build_suggestions

router = APIRouter(tags=["scores"])


@router.get("/scores", response_model=ScoreReport, summary="规则健康评分（非诊断）")
def get_scores(
    session: SessionDep,
    member_id: Annotated[str | None, Query(alias="memberId")] = None,
) -> ScoreReport:
    return build_score_report(session, member_id=member_id)


@router.get("/suggestions", response_model=SuggestionList, summary="规则健康建议")
def get_suggestions(
    session: SessionDep,
    member_id: Annotated[str | None, Query(alias="memberId")] = None,
) -> SuggestionList:
    report = build_score_report(session, member_id=member_id)
    return SuggestionList(items=build_suggestions(report))


__all__ = ["router"]

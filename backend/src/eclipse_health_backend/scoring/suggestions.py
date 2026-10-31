"""规则建议模板（G2）。

建议只由评分结果与缺失项决定，不调用 LLM；``prompt`` 是交给助手的预置问题。
"""

from __future__ import annotations

from .models import CategoryId, ScoreReport, Suggestion
from .service import CATEGORY_LABELS, CATEGORY_ORDER

_LOWEST_TEMPLATES: dict[str, tuple[str, str]] = {
    "heart": (
        "关注静息心率与心率变异，保持规律作息并减少过量咖啡因。",
        "观察我最近的心率和 HRV 数据，分析可以改善的点。",
    ),
    "sleep": (
        "尝试固定入睡时间，目标每晚 7–9 小时。",
        "观察我最近的睡眠数据，分析可以改善的点。",
    ),
    "weight": (
        "通过均衡饮食和规律运动，让 BMI 靠近 18.5–23.9。",
        "结合我的体重和身高，给出温和的生活方式建议。",
    ),
    "activity": (
        "把每日步数逐步提升到 8000 步。",
        "观察我最近的活动数据，给出循序渐进的步数目标。",
    ),
    "blood_pressure": (
        "在固定时间测量血压并连续记录，便于观察趋势。",
        "观察我最近的血压记录，分析趋势和需要注意的地方。",
    ),
}

_MISSING_TEMPLATES: dict[str, tuple[str, str]] = {
    "heart": (
        "补充静息心率或心电图分析，可让心脏评分更完整。",
        "我的静息心率和 HRV 数据可以从哪里导入？",
    ),
    "sleep": (
        "补充睡眠记录，可让睡眠评分更完整。",
        "怎样导入 Apple 健康或小米运动的睡眠记录？",
    ),
    "weight": (
        "在档案中补充身高和体重，可生成 BMI 评分。",
        "我应该在档案里补充身高和体重吗？",
    ),
    "activity": (
        "补充每日步数，可让活动评分更完整。",
        "怎样导入或记录每日步数？",
    ),
    "blood_pressure": (
        "补充血压记录，可让血压评分更完整。",
        "怎样录入手动血压或导入血压记录？",
    ),
}


def _missing_categories(report: ScoreReport) -> list[CategoryId]:
    missing_labels = set(report.missing)
    return [item for item in CATEGORY_ORDER if CATEGORY_LABELS[item] in missing_labels]


def build_suggestions(report: ScoreReport) -> list[Suggestion]:
    if report.overall is None:
        return [
            Suggestion(
                id="import-health-data",
                text="先导入健康数据或完成一次心电图分析，才能生成参考评分和建议。",
                category="general",
                severity="info",
                prompt="我可以先导入哪些健康数据？",
            )
        ]

    ranked: list[tuple[int, Suggestion]] = []
    available = [item for item in report.categories if item.score is not None]
    missing = _missing_categories(report)

    if available:
        lowest = min(
            available,
            key=lambda item: (
                item.score if item.score is not None else 101,
                CATEGORY_ORDER.index(item.id),
            ),
        )
        score = lowest.score if lowest.score is not None else 0
        if score < 85 or not missing:
            if score >= 85:
                suggestion = Suggestion(
                    id="keep-habits",
                    text="各项指标都在参考区间内，继续保持当前作息和活动习惯。",
                    category="general",
                    severity="info",
                    prompt="结合我最近的评分，给我一份保持健康习惯的清单。",
                )
            else:
                text, prompt = _LOWEST_TEMPLATES[lowest.id]
                suggestion = Suggestion(
                    id=f"improve-{lowest.id}",
                    text=text,
                    category=lowest.id,
                    severity="attention" if score < 70 else "info",
                    prompt=prompt,
                )
            ranked.append((score, suggestion))

    for index, category_id in enumerate(missing):
        if not available and index > 0:
            # 完全无数据时只给一条总导入建议，避免入口过多。
            break
        text, prompt = _MISSING_TEMPLATES[category_id]
        ranked.append(
            (
                100 + CATEGORY_ORDER.index(category_id),
                Suggestion(
                    id=f"missing-{category_id}",
                    text=text,
                    category=category_id,
                    severity="info",
                    prompt=prompt,
                ),
            )
        )

    ranked.sort(
        key=lambda item: (
            0 if item[1].severity == "attention" else 1,
            item[0],
            item[1].id,
        )
    )
    return [suggestion for _priority, suggestion in ranked[:3]]


__all__ = ["build_suggestions"]

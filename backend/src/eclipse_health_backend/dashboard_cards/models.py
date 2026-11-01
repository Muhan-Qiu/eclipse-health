"""自定义仪表盘卡片的请求 / 响应模型。

字段白名单是事实源：``kind`` / ``aggregation`` / ``view`` / ``colorToken``
只接受这里声明的枚举。助手工具与 REST API 共用同一套模型，因此不存在
「工具能绕过校验」的旁路。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CardKind = Literal[
    "steps",
    "heart-rate",
    "sleep",
    "body-mass",
    "blood-pressure",
    "exercise",
    "spo2",
    "stress",
    "glucose",
]

CardAggregation = Literal["latest", "avg", "min", "max", "sum", "count"]

CardView = Literal["stat", "sparkline", "line", "bar"]

CardCreator = Literal["user", "agent"]

ColorToken = Literal[
    "signal",
    "accent",
    "chart-1",
    "chart-2",
    "chart-3",
    "chart-4",
    "chart-5",
]

MAX_TITLE = 80
MAX_UNIT = 16
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 365


class CardFields(BaseModel):
    """可创建 / 可编辑的卡片字段；``extra="forbid"`` 拒绝任何未声明的键。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    kind: CardKind
    aggregation: CardAggregation = "latest"
    windowDays: int = Field(default=30, ge=MIN_WINDOW_DAYS, le=MAX_WINDOW_DAYS)
    view: CardView = "stat"
    unit: str | None = Field(default=None, max_length=MAX_UNIT)
    colorToken: ColorToken = "signal"


class DashboardCardCreate(CardFields):
    memberId: str | None = Field(default=None, max_length=64)
    createdBy: CardCreator = "user"


class DashboardCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    kind: CardKind | None = None
    aggregation: CardAggregation | None = None
    windowDays: int | None = Field(
        default=None, ge=MIN_WINDOW_DAYS, le=MAX_WINDOW_DAYS
    )
    view: CardView | None = None
    unit: str | None = Field(default=None, max_length=MAX_UNIT)
    colorToken: ColorToken | None = None


class CardPoint(BaseModel):
    t: str
    value: float


class CardData(BaseModel):
    """一张卡片在当前成员、当前时间窗下的聚合结果。

    ``value`` 为 ``None`` 表示没有数据，**绝不用 0 冒充**。
    """

    cardId: str
    kind: CardKind
    aggregation: CardAggregation
    value: float | None = None
    secondaryValue: float | None = None
    series: list[CardPoint] = Field(default_factory=list)
    unit: str | None = None
    unitSource: Literal["card", "kind", "missing"] = "missing"
    hasData: bool = False
    sampleCount: int = 0
    windowDays: int = 30
    missingReason: str | None = None


class DashboardCard(BaseModel):
    id: str
    memberId: str
    title: str
    kind: CardKind
    aggregation: CardAggregation
    windowDays: int
    view: CardView
    unit: str | None = None
    colorToken: ColorToken
    createdBy: CardCreator
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class DashboardCardOut(DashboardCard):
    data: CardData | None = None


class DashboardCardList(BaseModel):
    items: list[DashboardCardOut] = Field(default_factory=list)


class CardTemplate(BaseModel):
    id: str
    title: str
    kind: CardKind
    aggregation: CardAggregation
    windowDays: int
    view: CardView
    unit: str | None = None
    colorToken: ColorToken = "signal"


class DashboardCardDraft(BaseModel):
    id: str
    memberId: str
    card: CardFields
    createdBy: CardCreator
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    preview: CardData | None = None


class DashboardCardDraftList(BaseModel):
    items: list[DashboardCardDraft] = Field(default_factory=list)


__all__ = [
    "CardAggregation",
    "CardCreator",
    "CardData",
    "CardFields",
    "CardKind",
    "CardPoint",
    "CardTemplate",
    "CardView",
    "ColorToken",
    "DashboardCard",
    "DashboardCardCreate",
    "DashboardCardDraft",
    "DashboardCardDraftList",
    "DashboardCardList",
    "DashboardCardOut",
    "DashboardCardUpdate",
]

/** 自定义仪表盘卡片（A8）的前端类型，与后端 camelCase 响应对齐。 */

export type CustomCardKind =
  | "steps"
  | "heart-rate"
  | "sleep"
  | "body-mass"
  | "blood-pressure"
  | "exercise"
  | "spo2"
  | "stress"
  | "glucose";

export type CardAggregation =
  | "latest"
  | "avg"
  | "min"
  | "max"
  | "sum"
  | "count";

export type CardView = "stat" | "sparkline" | "line" | "bar";

export type CardCreator = "user" | "agent";

export type ColorToken =
  | "signal"
  | "accent"
  | "chart-1"
  | "chart-2"
  | "chart-3"
  | "chart-4"
  | "chart-5";

export interface CardPoint {
  t: string;
  value: number;
}

export interface CardData {
  cardId: string;
  kind: CustomCardKind;
  aggregation: CardAggregation;
  value: number | null;
  secondaryValue: number | null;
  series: CardPoint[];
  unit: string | null;
  unitSource: "card" | "kind" | "missing";
  hasData: boolean;
  sampleCount: number;
  windowDays: number;
  missingReason: string | null;
}

export interface DashboardCard {
  id: string;
  memberId: string;
  title: string;
  kind: CustomCardKind;
  aggregation: CardAggregation;
  windowDays: number;
  view: CardView;
  unit: string | null;
  colorToken: ColorToken;
  createdBy: CardCreator;
  createdAt: string;
  updatedAt: string;
  data?: CardData | null;
}

export interface CardFields {
  title: string;
  kind: CustomCardKind;
  aggregation: CardAggregation;
  windowDays: number;
  view: CardView;
  unit: string | null;
  colorToken: ColorToken;
}

export interface CardCreateInput extends CardFields {
  memberId?: string;
  createdBy?: CardCreator;
}

export interface CardTemplate {
  id: string;
  title: string;
  kind: CustomCardKind;
  aggregation: CardAggregation;
  windowDays: number;
  view: CardView;
  unit: string | null;
  colorToken: ColorToken;
}

export interface CardDraft {
  id: string;
  memberId: string;
  card: CardFields;
  createdBy: CardCreator;
  createdAt: string;
  updatedAt: string;
  preview: CardData | null;
}

export const CUSTOM_CARD_KINDS: readonly CustomCardKind[] = [
  "steps",
  "heart-rate",
  "sleep",
  "body-mass",
  "blood-pressure",
  "exercise",
  "spo2",
  "stress",
  "glucose",
];

export const CARD_AGGREGATIONS: readonly CardAggregation[] = [
  "latest",
  "avg",
  "min",
  "max",
  "sum",
  "count",
];

export const CARD_VIEWS: readonly CardView[] = ["stat", "sparkline", "line", "bar"];

export const CARD_COLORS: readonly ColorToken[] = [
  "signal",
  "accent",
  "chart-1",
  "chart-2",
  "chart-3",
  "chart-4",
  "chart-5",
];

/** 颜色令牌 → 设计系统 CSS 变量；未知令牌退回落差信号色。 */
export function cardColor(token: ColorToken): string {
  switch (token) {
    case "accent":
      return "var(--eh-accent)";
    case "chart-1":
      return "var(--eh-chart-1)";
    case "chart-2":
      return "var(--eh-chart-2)";
    case "chart-3":
      return "var(--eh-chart-3)";
    case "chart-4":
      return "var(--eh-chart-4)";
    case "chart-5":
      return "var(--eh-chart-5)";
    default:
      return "var(--eh-signal)";
  }
}

/** 默认标题：数据类型 + 聚合方式。 */
export function autoCardTitle(
  kind: CustomCardKind,
  aggregation: CardAggregation,
  t: (key: string) => string,
): string {
  return `${t(`dashboard.customCards.kinds.${kind}`)} · ${t(
    `dashboard.customCards.aggregations.${aggregation}`,
  )}`;
}

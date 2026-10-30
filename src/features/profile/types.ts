/** 健康档案与手动指标的前端类型（与后端 `metrics.models` 对齐）。 */

export const METRIC_KINDS = [
  "blood_pressure",
  "weight",
  "spo2",
  "glucose",
] as const;

export type MetricKind = (typeof METRIC_KINDS)[number];

export const METRIC_UNITS: Record<MetricKind, string> = {
  blood_pressure: "mmHg",
  weight: "kg",
  spo2: "%",
  glucose: "mmol/L",
};

/** 价格/单位都是字符串，值统一用数字，按 kind 读取对应字段。 */
export interface MetricValues {
  systolic?: number;
  diastolic?: number;
  weight?: number;
  spo2?: number;
  glucose?: number;
}

export interface MetricWarning {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface Metric {
  id: string;
  memberId: string;
  kind: MetricKind;
  measuredAt: string;
  timezone: string;
  values: MetricValues;
  unit: string;
  notes: string;
  tags: string[];
  warnings: MetricWarning[];
  createdAt: string;
  updatedAt: string;
}

export interface MetricPage {
  items: Metric[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetricListParams {
  kind?: MetricKind;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export interface MetricInput {
  kind: MetricKind;
  measuredAt: string;
  values: MetricValues;
  notes?: string;
  tags?: string[];
  timezone?: string;
  memberId?: string;
}

export interface MetricPatch {
  measuredAt?: string;
  values?: MetricValues;
  notes?: string;
  tags?: string[];
  timezone?: string;
}

export type MemberSex = "female" | "male" | "other" | "unknown";

export interface MemberPatch {
  birthYear?: number | null;
  sex?: MemberSex;
  heightCm?: number | null;
  weightKg?: number | null;
  conditions?: string[];
  medications?: string[];
  notes?: string;
}

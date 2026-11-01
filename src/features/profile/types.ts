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
  restingHeartRate?: number | null;
  sleepStart?: string | null;
  sleepEnd?: string | null;
  sleepTimezone?: string | null;
  conditions?: string[];
  medications?: string[];
  notes?: string;
}

/** 共享 `Member` 类型尚未包含 G3 字段，这里做局部扩展，避免改 lib/api/types。 */
export interface ProfileMember {
  restingHeartRate?: number | null;
  sleepStart?: string | null;
  sleepEnd?: string | null;
  sleepTimezone?: string | null;
}

export const EXERCISE_ACTIVITIES = [
  "walk",
  "run",
  "cycle",
  "swim",
  "strength",
  "yoga",
  "other",
] as const;

export type ExerciseActivity = (typeof EXERCISE_ACTIVITIES)[number];
export type ExerciseIntensity = "low" | "moderate" | "vigorous";
export type ExerciseSubjective = "轻松" | "适中" | "吃力";
export type ExerciseSource = "manual" | "import";

export interface Exercise {
  id: string;
  memberId: string;
  activity: ExerciseActivity;
  durationSec: number;
  distanceKm: number | null;
  intensity: ExerciseIntensity | null;
  subjective: ExerciseSubjective | null;
  notes: string;
  startAt: string;
  source: ExerciseSource;
  createdAt: string;
  updatedAt: string;
}

export interface ExercisePage {
  items: Exercise[];
  total: number;
  limit: number;
  offset: number;
}

export interface ExerciseInput {
  activity: ExerciseActivity;
  durationSec: number;
  distanceKm?: number | null;
  intensity?: ExerciseIntensity | null;
  subjective?: ExerciseSubjective | null;
  notes?: string;
  startAt: string;
  timezone?: string;
  memberId?: string;
}

export interface MemoryDocument {
  content: string;
  enabled: boolean;
  updatedAt: string | null;
}

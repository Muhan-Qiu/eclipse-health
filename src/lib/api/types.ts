/** 与后端 OpenAPI 对齐的类型（camelCase，时间 RFC 3339）。 */

export type DeviceVendor = "apple" | "samsung" | "huawei" | "generic";

export interface DeviceInfo {
  vendor: DeviceVendor;
  model: string;
}

export type RecordStatus = "ready" | "analyzing" | "analyzed" | "failed";

/** 列表接口附带的最新分析状态（B3-02）；单条记录接口不返回这组字段。 */
export type LatestAnalysisStatus =
  | "none"
  | "queued"
  | "running"
  | "completed"
  | "failed";

export interface RecordSummary {
  id: string;
  memberId: string;
  recordedAt: string;
  durationSec: number;
  device: DeviceInfo;
  tags: string[];
  leads: string[];
  sampleRateHz: number;
  status: RecordStatus;
  /** 最新分析状态原始值；`status` 由它派生，保留以兼容既有组件。 */
  analysisStatus: LatestAnalysisStatus;
  latestAnalysisId: string | null;
  latestAnalyzedAt: string | null;
  /** 仅 mock 数据为 true；真实记录必须显示为真实数据。 */
  isDemo: boolean;
  /** 内置 MIT-BIH 示例记录（A1）：真实导入，但不是用户数据。 */
  isSample: boolean;
  /** 用户收藏（D1）。 */
  favorite: boolean;
  notes: string;
  signalCount: number;
  qualityScore: number | null;
}

/* ------------------------------------------------------------------ *
 * 后端数据形状（docs/INTERNAL_API_V1.md、DATA_SCHEMA_V1.md）
 * ------------------------------------------------------------------ */

export interface SourceInfo {
  kind?: "wearable" | "device" | "manual" | "file" | "import" | "unknown";
  manufacturer?: string | null;
  device?: string | null;
  app?: string | null;
  appVersion?: string | null;
}

export interface QualityWarning {
  code: string;
  severity: "info" | "warning" | "error";
  startSec?: number | null;
  endSec?: number | null;
  message?: string;
}

export interface QualitySegment {
  startSec: number;
  endSec: number;
  quality: number;
}

export interface Quality {
  score: number | null;
  level: "good" | "fair" | "poor" | null;
  warnings: QualityWarning[];
  segments: QualitySegment[];
}

export interface Provenance {
  fileNameHash?: string | null;
  fileHash?: string | null;
  adapterVersion?: string | null;
}

export interface HealthRecord {
  schema?: string;
  id: string;
  memberId: string;
  recordType: string;
  moduleId?: string | null;
  capturedAt: string;
  timezone: string;
  source: SourceInfo;
  samplingRate: number | null;
  leads: string[];
  durationSec: number | null;
  unit: string;
  signalIds: string[];
  quality?: Quality | null;
  tags: string[];
  notes: string;
  favorite?: boolean;
  metadata: Record<string, unknown>;
  payload: Record<string, unknown>;
  provenance?: Provenance | null;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string | null;
  /** 仅 `GET /records` 列表项返回（B3-02）；单条查询不带。 */
  latestAnalysisStatus?: LatestAnalysisStatus | null;
  latestAnalysisId?: string | null;
  latestAnalyzedAt?: string | null;
}

export interface RecordPage {
  items: HealthRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface SignalStorageInfo {
  kind: "file";
  relativePath: string;
  sha256: string;
  byteOrder: "little";
}

export interface SignalMetadata {
  schema?: string;
  id: string;
  recordId: string;
  lead: string;
  fs: number;
  unit: string;
  dtype: "float32";
  shape: number[];
  startSample: number;
  storage: SignalStorageInfo;
  createdAt: string;
}

export interface SignalData {
  recordId: string;
  lead: string;
  fs: number;
  unit: string;
  samples: Float32Array;
  sampleCount: number;
  sha256?: string;
}

export type BeatLabel = "N" | "SVEB" | "VEB" | "F" | string;

export interface Beat {
  index: number;
  rPeakSample: number;
  label: BeatLabel;
  confidence: number;
  rrPrevMs: number | null;
  rrNextMs?: number | null;
  probabilities: Record<string, number>;
}

export interface Measurement {
  schema?: string;
  id: string;
  recordId?: string;
  analysisId?: string;
  code: string;
  label: string;
  value: number | null;
  unit: string;
  ucum: string;
  range?: { startSec: number; endSec: number } | null;
  confidence: number | null;
  method: string;
  warnings: QualityWarning[];
}

export type AnalysisStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type AnalysisStage =
  | "quality"
  | "features"
  | "inference"
  | "measurements"
  | "summary"
  | string;

export interface AnalysisProgress {
  stage: AnalysisStage;
  percent: number;
}

export interface AnalysisError {
  code: string;
  message: string;
}

export interface AnalysisResult {
  schema?: string;
  id: string;
  recordId: string;
  moduleId: string;
  modelId: string;
  modelVersion: string;
  task: string;
  status: AnalysisStatus;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  summary: string;
  quality: Quality;
  measurements: Measurement[];
  beats: Beat[];
  annotations?: unknown[];
  warnings: QualityWarning[];
  parameters?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  progress?: AnalysisProgress | null;
  error?: AnalysisError | null;
}

export interface AnalysisListResponse {
  items: AnalysisResult[];
}

export interface AnalysisStartResponse {
  analysisId: string;
  recordId: string;
  status: AnalysisStatus;
  engine: string;
}

export interface AnalysisStartBody {
  engine?: string;
  options?: {
    allowShortRecord?: boolean;
    [key: string]: unknown;
  };
}

export interface EngineStatus {
  status: "warming" | "ready" | "error";
  engine: string;
  moduleId: string;
  modelId: string;
  modelVersion: string;
  message?: string | null;
  startedAt?: string | null;
  readyAt?: string | null;
}

export interface Member {
  schema?: string;
  id: string;
  displayName: string;
  birthYear?: number | null;
  sex?: "female" | "male" | "other" | "unknown";
  heightCm?: number | null;
  weightKg?: number | null;
  conditions?: string[];
  medications?: string[];
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface HealthStatus {
  status: "ok" | "degraded" | string;
  version: string;
  mock: boolean;
}

export interface ImportRequires {
  samplingRate: boolean;
  lead: boolean;
  unit: boolean;
}

export interface ImportWarning {
  code: string;
  severity?: "info" | "warning" | "error";
  message: string;
  startSec?: number | null;
  endSec?: number | null;
}

export interface ImportPreviewSamples {
  nSamples: number;
  samples: number[];
}

export interface ImportPreview {
  importId: string;
  format: string;
  adapterId: string;
  fileNameHash?: string;
  fileHash?: string;
  samplingRate: number | null;
  leads: string[];
  durationSec: number | null;
  unit: string;
  requires: ImportRequires;
  warnings: ImportWarning[];
  preview: ImportPreviewSamples;
  hasAnnotations?: boolean;
  annotationCount?: number;
}

export interface ImportParameters {
  samplingRate?: number | null;
  lead?: string | null;
  unit?: string | null;
  polarity?: "normal" | "inverted";
}

export interface ImportCommitBody {
  memberId: string;
  capturedAt: string;
  timezone: string;
  tags?: string[];
  notes?: string;
  parameters?: ImportParameters;
}

export interface ImportCommitResponse {
  recordId: string;
  record: HealthRecord;
}

export type ImportHintFormat = "wfdb" | "csv" | "auto";

/* ------------------------------------------------------------------ *
 * 内置示例记录（A1 · POST /imports/samples/{sampleId}）
 * ------------------------------------------------------------------ */

export type SampleRecordId = "mitdb-100" | "mitdb-200" | "mitdb-208";

export interface SampleImportBody {
  memberId?: string;
  capturedAt?: string;
  timezone?: string;
  /** 导入后异步发起 Cardia 分析；失败不影响记录创建。 */
  startAnalysis?: boolean;
}

export interface SampleImportResponse {
  recordId: string;
  analysisId: string | null;
}

/* ------------------------------------------------------------------ *
 * 趋势与对比（B3-02 / GET /trends、GET /records/compare）
 * ------------------------------------------------------------------ */

export interface TrendPoint {
  /** 记录采集时间（RFC 3339）。 */
  t: string;
  value: number;
  recordId: string;
  analysisId: string;
}

export interface TrendSummary {
  min: number | null;
  max: number | null;
  mean: number | null;
  count: number;
}

export interface TrendSeries {
  metric: string;
  label: string;
  unit: string;
  ucum: string;
  points: TrendPoint[];
  summary: TrendSummary;
}

export interface TrendsResponse {
  series: TrendSeries[];
}

export interface CompareAnalysis {
  recordId: string;
  /** 最新一次完成分析的摘要 + measurements；没有则为 null。 */
  latestCompleted: AnalysisResult | null;
}

export interface RecordCompareResponse {
  records: HealthRecord[];
  analyses: CompareAnalysis[];
}

/* ------------------------------------------------------------------ *
 * 健康数据（B4 导入 · C3 页面）
 * 记录类型固定为 `org.eclipsehealth.health.<kind>`。
 * ------------------------------------------------------------------ */

export type HealthRecordKind =
  | "steps"
  | "heart-rate"
  | "sleep"
  | "body-mass"
  | "blood-pressure";

/** 健康数据记录的 payload 约定之一（见 DATA_SCHEMA_V1）。 */
export interface HealthRecordPayload {
  value?: number | string | { systolic?: number; diastolic?: number } | null;
  unit?: string;
  startAt?: string | null;
  endAt?: string | null;
  sourceApp?: string | null;
}

/* ------------------------------------------------------------------ *
 * 健康评分与建议（G2 · GET /scores、GET /suggestions）
 * ------------------------------------------------------------------ */

export type ScoreGrade = "excellent" | "good" | "fair" | "attention" | "unknown";

export interface ScoreCategory {
  id: "heart" | "sleep" | "weight" | "activity" | "blood-pressure" | string;
  label: string;
  score: number;
  grade: ScoreGrade;
  factors: string[];
  missing: string | null;
  evidenceCount: number;
}

export interface MissingScore {
  id: string;
  reason: string;
}

export interface HealthScores {
  overall: number | null;
  generatedAt: string;
  categories: ScoreCategory[];
  missing: MissingScore[];
}

export type SuggestionSeverity = "info" | "attention";

export interface HealthSuggestion {
  id: string;
  text: string;
  category: string;
  severity: SuggestionSeverity;
  /** 点击「和教练聊聊」时预置到助手输入框的问题。 */
  prompt: string;
}

export interface SuggestionList {
  items: HealthSuggestion[];
}


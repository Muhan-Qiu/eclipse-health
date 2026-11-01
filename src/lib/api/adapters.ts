import type {
  AnalysisListResponse,
  AnalysisProgress,
  AnalysisResult,
  AnalysisStatus,
  Beat,
  CompareAnalysis,
  DeviceInfo,
  DeviceVendor,
  EngineStatus,
  HealthRecord,
  HealthRecordKind,
  HealthScores,
  HealthSuggestion,
  ImportPreview,
  ImportRequires,
  LatestAnalysisStatus,
  Measurement,
  MissingScore,
  Quality,
  QualitySegment,
  QualityWarning,
  RecordCompareResponse,
  RecordStatus,
  RecordSummary,
  ScoreCategory,
  ScoreGrade,
  SourceInfo,
  SuggestionList,
  SuggestionSeverity,
  TrendPoint,
  TrendSeries,
  TrendSummary,
  TrendsResponse,
} from "./types";

type Raw = Record<string, unknown>;

function asObject(value: unknown): Raw {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Raw)
    : {};
}

function pick(raw: Raw, camel: string, snake?: string): unknown {
  if (raw[camel] !== undefined) return raw[camel];
  return snake ? raw[snake] : undefined;
}

function num(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nullableNum(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function arr<T>(value: unknown, map: (item: unknown, index: number) => T): T[] {
  return Array.isArray(value) ? value.map(map) : [];
}

/** 从 source 推导 UI 设备信息；后端没有 `device` 对象这一字段。 */
export function deviceFromSource(source: SourceInfo | undefined | null): DeviceInfo {
  const raw = asObject(source);
  const manufacturer = str(raw.manufacturer).trim();
  const model = str(raw.device ?? raw.model).trim();
  const signature = `${manufacturer} ${model}`.toLowerCase();

  let vendor: DeviceVendor = "generic";
  if (signature.includes("apple")) vendor = "apple";
  else if (signature.includes("samsung") || signature.includes("galaxy"))
    vendor = "samsung";
  else if (signature.includes("huawei") || signature.includes("watch gt"))
    vendor = "huawei";

  const label = [manufacturer, model].filter(Boolean).join(" ");
  return { vendor, model: label };
}

function normalizeQuality(raw: unknown): Quality {
  const source = asObject(raw);
  const level = str(source.level);
  return {
    score: nullableNum(source.score),
    level:
      level === "good" || level === "fair" || level === "poor" ? level : null,
    warnings: arr(source.warnings, normalizeWarning),
    segments: arr(source.segments, (segment): QualitySegment => {
      const item = asObject(segment);
      return {
        startSec: num(pick(item, "startSec", "start_sec")),
        endSec: num(pick(item, "endSec", "end_sec")),
        quality: num(item.quality),
      };
    }),
  };
}

export function normalizeWarning(value: unknown): QualityWarning {
  const item = asObject(value);
  const severity = str(item.severity, "warning");
  return {
    code: str(item.code, "unknown"),
    severity:
      severity === "info" || severity === "error" || severity === "warning"
        ? severity
        : "warning",
    startSec: nullableNum(pick(item, "startSec", "start_sec")),
    endSec: nullableNum(pick(item, "endSec", "end_sec")),
    message: str(item.message),
  };
}

function normalizeMeasurement(value: unknown): Measurement {
  const item = asObject(value);
  const range = asObject(item.range);
  return {
    schema: typeof item.schema === "string" ? item.schema : undefined,
    id: str(item.id, `msr_${str(item.code, "unknown")}`),
    recordId: typeof item.recordId === "string" ? item.recordId : undefined,
    analysisId: typeof item.analysisId === "string" ? item.analysisId : undefined,
    code: str(item.code, "unknown"),
    label: str(item.label, str(item.code, "—")),
    value: nullableNum(item.value),
    unit: str(item.unit),
    ucum: str(item.ucum),
    range:
      range.startSec === undefined && range.endSec === undefined
        ? null
        : {
            startSec: num(pick(range, "startSec", "start_sec")),
            endSec: num(pick(range, "endSec", "end_sec")),
          },
    confidence: nullableNum(item.confidence),
    method: str(item.method),
    warnings: arr(item.warnings, normalizeWarning),
  };
}

function normalizeBeat(value: unknown, index: number): Beat {
  const item = asObject(value);
  const label = str(item.label, "N");
  const probabilities = asObject(item.probabilities);
  const normalized: Record<string, number> = {};
  for (const [key, probability] of Object.entries(probabilities)) {
    normalized[key] = num(probability);
  }
  if (Object.keys(normalized).length === 0) {
    normalized[label] = num(item.confidence, 1);
  }
  return {
    index: Math.trunc(num(item.index, index)),
    rPeakSample: Math.trunc(
      num(pick(item, "rPeakSample", "r_peak_sample")),
    ),
    label,
    confidence: num(item.confidence),
    rrPrevMs: nullableNum(pick(item, "rrPrevMs", "rr_prev_ms")),
    rrNextMs: nullableNum(pick(item, "rrNextMs", "rr_next_ms")),
    probabilities: normalized,
  };
}

function normalizeStatus(value: unknown): AnalysisStatus {
  const status = str(value, "completed");
  if (
    status === "queued" ||
    status === "running" ||
    status === "completed" ||
    status === "failed" ||
    status === "cancelled"
  ) {
    return status;
  }
  return "completed";
}

function normalizeProgress(value: unknown): AnalysisProgress | null {
  if (value === null || value === undefined) return null;
  const item = asObject(value);
  if (Object.keys(item).length === 0) return null;
  return {
    stage: str(item.stage, "summary"),
    percent: Math.max(0, Math.min(100, num(item.percent))),
  };
}

/** 后端可能把 snake_case（引擎内部）直接透出，这里统一成 camelCase。 */
export function normalizeAnalysis(value: unknown): AnalysisResult {
  const outer = asObject(value);
  const item = asObject(outer.analysis ?? outer.result ?? value);
  const error = asObject(item.error);
  return {
    schema: typeof item.schema === "string" ? item.schema : undefined,
    id: str(item.id, str(item.analysisId, "")),
    recordId: str(pick(item, "recordId", "record_id")),
    moduleId: str(pick(item, "moduleId", "module_id")),
    modelId: str(pick(item, "modelId", "model_id")),
    modelVersion: str(pick(item, "modelVersion", "model_version")),
    task: str(item.task, "beat-classification"),
    status: normalizeStatus(item.status),
    startedAt: item.startedAt
      ? str(item.startedAt)
      : item.started_at
        ? str(item.started_at)
        : null,
    completedAt: item.completedAt
      ? str(item.completedAt)
      : item.completed_at
        ? str(item.completed_at)
        : null,
    durationMs: nullableNum(pick(item, "durationMs", "duration_ms")),
    summary: str(item.summary),
    quality: normalizeQuality(item.quality),
    measurements: arr(item.measurements, normalizeMeasurement),
    beats: arr(item.beats, normalizeBeat),
    annotations: Array.isArray(item.annotations) ? item.annotations : [],
    warnings: arr(item.warnings, normalizeWarning),
    parameters: asObject(item.parameters),
    provenance: asObject(item.provenance),
    progress: normalizeProgress(item.progress),
    error:
      error.code === undefined && error.message === undefined
        ? null
        : { code: str(error.code, "analysis_failed"), message: str(error.message) },
  };
}

export function normalizeAnalysisList(value: unknown): AnalysisListResponse {
  if (Array.isArray(value)) return { items: value.map(normalizeAnalysis) };
  const item = asObject(value);
  return { items: arr(item.items, normalizeAnalysis) };
}

export function normalizeEngine(value: unknown): EngineStatus {
  const item = asObject(value);
  const status = str(item.status, "warming");
  return {
    status:
      status === "ready" || status === "error" || status === "warming"
        ? status
        : "warming",
    engine: str(item.engine, "cardia"),
    moduleId: str(pick(item, "moduleId", "module_id")),
    modelId: str(pick(item, "modelId", "model_id")),
    modelVersion: str(pick(item, "modelVersion", "model_version")),
    message: typeof item.message === "string" ? item.message : null,
    startedAt: typeof item.startedAt === "string" ? item.startedAt : null,
    readyAt: typeof item.readyAt === "string" ? item.readyAt : null,
  };
}

export function normalizeImportPreview(value: unknown): ImportPreview {
  const item = asObject(value);
  const preview = asObject(item.preview);
  const rawLeads = Array.isArray(item.leads) ? item.leads : [];
  const leads = rawLeads.map((lead) =>
    typeof lead === "string" ? lead : str(asObject(lead).lead),
  );
  const samplingRate = pick(item, "samplingRate", "sampling_rate");
  const rawRequires = asObject(item.requires);
  const requiredSamplingRate =
    rawRequires.samplingRate ??
    rawRequires.sampling_rate ??
    (samplingRate === null || samplingRate === undefined);
  const requires: ImportRequires = {
    samplingRate: Boolean(requiredSamplingRate),
    lead: Boolean(rawRequires.lead ?? leads.length === 0),
    unit: Boolean(rawRequires.unit ?? !item.unit),
  };
  const rawSamples = Array.isArray(preview.samples)
    ? preview.samples
    : Array.isArray(item.samples)
      ? item.samples
      : [];

  return {
    importId: str(pick(item, "importId", "import_id")),
    format: str(item.format, "unknown"),
    adapterId: str(pick(item, "adapterId", "adapter_id")),
    fileNameHash: typeof item.fileNameHash === "string" ? item.fileNameHash : undefined,
    fileHash: typeof item.fileHash === "string" ? item.fileHash : undefined,
    samplingRate: nullableNum(samplingRate),
    leads,
    durationSec: nullableNum(pick(item, "durationSec", "duration_sec")),
    unit: str(item.unit, "mV"),
    requires,
    warnings: arr(item.warnings, (value) => {
      const warning = normalizeWarning(value);
      return {
        code: warning.code,
        severity: warning.severity,
        message: warning.message ?? warning.code,
        startSec: warning.startSec,
        endSec: warning.endSec,
      };
    }),
    preview: {
      nSamples: Math.trunc(num(pick(preview, "nSamples", "n_samples"), rawSamples.length)),
      samples: rawSamples.map((sample) => num(sample)),
    },
    hasAnnotations: Boolean(
      pick(item, "hasAnnotations", "has_annotations") ?? false,
    ),
    annotationCount: Math.trunc(
      num(pick(item, "annotationCount", "annotation_count"), 0),
    ),
  };
}

/** 后端 HealthRecord -> UI RecordSummary（契约 §5）。 */
export function toRecordSummary(
  record: HealthRecord,
  analysisStatus?: RecordStatus,
): RecordSummary {
  const signalCount = record.signalIds?.length ?? 0;
  const latest = normalizeLatestAnalysisStatus(record.latestAnalysisStatus);
  let status: RecordStatus;
  if (analysisStatus) {
    status = analysisStatus;
  } else if (latest === "completed") {
    status = "analyzed";
  } else if (latest === "queued" || latest === "running") {
    status = "analyzing";
  } else if (latest === "failed") {
    status = "failed";
  } else {
    status = signalCount > 0 ? "ready" : "failed";
  }

  return {
    id: record.id,
    memberId: record.memberId,
    recordedAt: record.capturedAt,
    durationSec: record.durationSec ?? 0,
    device: deviceFromSource(record.source),
    tags: record.tags ?? [],
    leads: record.leads ?? [],
    sampleRateHz: record.samplingRate ?? 0,
    status,
    analysisStatus: latest,
    latestAnalysisId: record.latestAnalysisId ?? null,
    latestAnalyzedAt: record.latestAnalyzedAt ?? null,
    isDemo:
      record.metadata?.demo === true || record.metadata?.mock === true,
    isSample: record.metadata?.isSample === true,
    favorite: record.favorite === true,
    notes: record.notes ?? "",
    signalCount,
    qualityScore: record.quality?.score ?? null,
  };
}

export function normalizeLatestAnalysisStatus(value: unknown): LatestAnalysisStatus {
  if (
    value === "queued" ||
    value === "running" ||
    value === "completed" ||
    value === "failed"
  ) {
    return value;
  }
  return "none";
}

function normalizeTrendSummary(value: unknown): TrendSummary {
  const item = asObject(value);
  return {
    min: nullableNum(item.min),
    max: nullableNum(item.max),
    mean: nullableNum(item.mean),
    count: Math.trunc(num(item.count, 0)),
  };
}

function normalizeTrendPoint(value: unknown): TrendPoint {
  const item = asObject(value);
  return {
    t: str(item.t),
    value: num(item.value),
    recordId: str(pick(item, "recordId", "record_id")),
    analysisId: str(pick(item, "analysisId", "analysis_id")),
  };
}

export function normalizeTrends(value: unknown): TrendsResponse {
  const item = asObject(value);
  const series: TrendSeries[] = arr(item.series, (entry) => {
    const raw = asObject(entry);
    const metric = str(raw.metric);
    return {
      metric,
      label: str(raw.label, metric),
      unit: str(raw.unit),
      ucum: str(raw.ucum),
      points: arr(raw.points, normalizeTrendPoint).filter(
        (point) => point.t !== "" && point.recordId !== "",
      ),
      summary: normalizeTrendSummary(raw.summary),
    };
  }).filter((entry) => entry.metric !== "");
  return { series };
}

export function normalizeCompare(value: unknown): RecordCompareResponse {
  const item = asObject(value);
  const analyses: CompareAnalysis[] = arr(item.analyses, (entry) => {
    const raw = asObject(entry);
    const latest = raw.latestCompleted;
    return {
      recordId: str(pick(raw, "recordId", "record_id")),
      latestCompleted:
        latest === null || latest === undefined ? null : normalizeAnalysis(latest),
    };
  });
  return {
    records: arr(item.records, (record) => record as HealthRecord),
    analyses,
  };
}

/** 列表流里的分析状态：running/queued -> analyzing，failed -> failed。 */
export function analysisStatusToRecordStatus(
  status: AnalysisStatus | undefined,
): RecordStatus | undefined {
  if (!status) return undefined;
  if (status === "running" || status === "queued") return "analyzing";
  if (status === "failed") return "failed";
  if (status === "completed") return "analyzed";
  return undefined;
}

/* ------------------------------------------------------------------ *
 * 健康评分与建议（G2）
 * ------------------------------------------------------------------ */

const SCORE_GRADES: readonly ScoreGrade[] = [
  "excellent",
  "good",
  "fair",
  "attention",
  "unknown",
];

function normalizeGrade(value: unknown): ScoreGrade {
  return (SCORE_GRADES as readonly string[]).includes(str(value))
    ? (str(value) as ScoreGrade)
    : "unknown";
}

function normalizeScoreCategory(value: unknown): ScoreCategory {
  const item = asObject(value);
  return {
    id: str(item.id, "unknown"),
    label: str(item.label, str(item.id, "—")),
    score: num(item.score, 0),
    grade: normalizeGrade(item.grade),
    factors: Array.isArray(item.factors)
      ? item.factors.filter((factor): factor is string => typeof factor === "string")
      : [],
    missing: typeof item.missing === "string" ? item.missing : null,
    evidenceCount: Math.trunc(num(item.evidenceCount, 0)),
  };
}

function normalizeMissingScore(value: unknown): MissingScore {
  const item = asObject(value);
  return {
    id: str(item.id, "unknown"),
    reason: str(item.reason),
  };
}

export function normalizeScores(value: unknown): HealthScores {
  const item = asObject(value);
  return {
    overall: nullableNum(item.overall),
    generatedAt: str(item.generatedAt),
    categories: arr(item.categories, normalizeScoreCategory).filter(
      (category) => category.id !== "unknown",
    ),
    missing: arr(item.missing, normalizeMissingScore),
  };
}

function normalizeSuggestion(value: unknown, index: number): HealthSuggestion {
  const item = asObject(value);
  const severity = str(item.severity, "info");
  return {
    id: str(item.id, `suggestion-${index}`),
    text: str(item.text),
    category: str(item.category, "general"),
    severity: (severity === "attention" ? "attention" : "info") as SuggestionSeverity,
    prompt: str(item.prompt, str(item.text)),
  };
}

export function normalizeSuggestions(value: unknown): SuggestionList {
  if (Array.isArray(value)) {
    return { items: value.map(normalizeSuggestion) };
  }
  const item = asObject(value);
  return {
    items: arr(item.items, normalizeSuggestion).filter(
      (suggestion) => suggestion.text !== "",
    ),
  };
}

/* ------------------------------------------------------------------ *
 * 健康数据（B4 导入 · C3 页面）
 * ------------------------------------------------------------------ */

export const HEALTH_RECORD_PREFIX = "org.eclipsehealth.health.";

export const HEALTH_KINDS: readonly HealthRecordKind[] = [
  "steps",
  "heart-rate",
  "resting-heart-rate",
  "sleep",
  "body-mass",
  "blood-pressure",
  "spo2",
  "stress",
  "workout",
  "respiratory-rate",
  "body-temperature",
  "blood-glucose",
  "hrv",
];

export type HealthSourceId =
  | "apple-health"
  | "samsung-health"
  | "xiaomi-mi-fitness"
  | "huawei-health"
  | "zepp"
  | "oppo-health"
  | "garmin-connect"
  | "fitbit"
  | "withings"
  | "google-fit"
  | "unknown";

export interface HealthWorkoutValue {
  activity: string | null;
  durationSec: number | null;
  distanceM: number | null;
  energyKcal: number | null;
  avgHeartRate: number | null;
}

export interface HealthRecordView {
  id: string;
  kind: HealthRecordKind;
  /** 步数/心率等数值；睡眠为 null（用 sleepStage），运动为 null（用 workout）。 */
  value: number | null;
  unit: string;
  systolic: number | null;
  diastolic: number | null;
  sleepStage: string | null;
  workout: HealthWorkoutValue | null;
  /** HRV 的指标名（rmssd / sdnn / pnn50 / lf / hf / lf-hf-ratio）。 */
  metric: string | null;
  startAt: string | null;
  endAt: string | null;
  durationSec: number | null;
  sourceId: HealthSourceId;
  importedAt: string;
  payload: Raw;
  metadata: Raw;
}


/** `org.eclipsehealth.health.<kind>` → kind；非健康记录返回 null。 */
export function healthKindOf(recordType: string): HealthRecordKind | null {
  if (!recordType.startsWith(HEALTH_RECORD_PREFIX)) return null;
  const suffix = recordType.slice(HEALTH_RECORD_PREFIX.length);
  return (HEALTH_KINDS as readonly string[]).includes(suffix)
    ? (suffix as HealthRecordKind)
    : null;
}

export function healthRecordType(kind: HealthRecordKind): string {
  return `${HEALTH_RECORD_PREFIX}${kind}`;
}

function healthSourceId(record: HealthRecord): HealthSourceId {
  const importSource = str(record.metadata?.importSource).toLowerCase();
  const app = `${str(record.source?.app)} ${str(record.source?.manufacturer)}`.toLowerCase();
  const haystack = `${importSource} ${app}`;
  if (haystack.includes("apple")) return "apple-health";
  if (haystack.includes("samsung")) return "samsung-health";
  if (haystack.includes("huawei") || haystack.includes("荣耀")) return "huawei-health";
  if (haystack.includes("xiaomi") || haystack.includes("mi fitness") || haystack.includes("zepp life")) {
    return "xiaomi-mi-fitness";
  }
  if (haystack.includes("zepp") || haystack.includes("amazfit")) return "zepp";
  if (haystack.includes("oppo")) return "oppo-health";
  if (haystack.includes("garmin")) return "garmin-connect";
  if (haystack.includes("fitbit")) return "fitbit";
  if (haystack.includes("withings")) return "withings";
  if (haystack.includes("google fit")) return "google-fit";
  return "unknown";
}

function durationBetween(startAt: string | null, endAt: string | null): number | null {
  if (!startAt || !endAt) return null;
  const start = Date.parse(startAt);
  const end = Date.parse(endAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return (end - start) / 1000;
}

/** Apple 用 `asleep-deep`，小米等导出用 `deep`/`light`/`rem`；统一成页面的键。 */
const SLEEP_STAGE_ALIASES: Record<string, string> = {
  "in-bed": "in-bed",
  in_bed: "in-bed",
  inbed: "in-bed",
  asleep: "asleep",
  sleep: "asleep",
  "asleep-core": "asleep-core",
  core: "asleep-core",
  light: "asleep-core",
  "asleep-deep": "asleep-deep",
  deep: "asleep-deep",
  "asleep-rem": "asleep-rem",
  rem: "asleep-rem",
  awake: "awake",
  wake: "awake",
};

export function normalizeSleepStage(value: string | null): string | null {
  if (!value) return null;
  return SLEEP_STAGE_ALIASES[value.trim().toLowerCase()] ?? "unknown";
}

/** 把一条健康数据记录整理成页面直接可用的视图（不含 i18n 文案）。 */
export function toHealthRecordView(
  record: HealthRecord,
  fallbackKind?: HealthRecordKind,
): HealthRecordView {
  const kind =
    healthKindOf(record.recordType) ??
    fallbackKind ??
    ("steps" as HealthRecordKind);
  const payload = asObject(record.payload);
  const rawValue = payload.value;

  let value: number | null = null;
  let systolic: number | null = null;
  let diastolic: number | null = null;
  let sleepStage: string | null = null;
  let workout: HealthWorkoutValue | null = null;
  let metric: string | null = null;

  if (kind === "blood-pressure") {
    const pair = asObject(rawValue);
    systolic = nullableNum(pair.systolic);
    diastolic = nullableNum(pair.diastolic);
  } else if (kind === "sleep") {
    sleepStage = normalizeSleepStage(
      typeof rawValue === "string" ? rawValue : null,
    );
  } else if (kind === "workout") {
    const item = asObject(rawValue);
    workout = {
      activity: typeof item.activity === "string" ? item.activity : null,
      durationSec: nullableNum(item.durationSec),
      distanceM: nullableNum(item.distanceM),
      energyKcal: nullableNum(item.energyKcal),
      avgHeartRate: nullableNum(item.avgHeartRate),
    };
  } else if (kind === "hrv") {
    const item = asObject(rawValue);
    metric = typeof item.metric === "string" ? item.metric : null;
    value = nullableNum(item.value);
  } else {
    value = nullableNum(rawValue);
  }

  const startAt =
    typeof payload.startAt === "string" ? payload.startAt : record.capturedAt;
  const endAt = typeof payload.endAt === "string" ? payload.endAt : null;
  const durationSec =
    record.durationSec ?? durationBetween(startAt, endAt);

  return {
    id: record.id,
    kind,
    value,
    unit: str(payload.unit) || record.unit || "",
    systolic,
    diastolic,
    sleepStage,
    workout,
    metric,
    startAt,
    endAt,
    durationSec: durationSec !== null && durationSec >= 0 ? durationSec : null,
    sourceId: healthSourceId(record),
    importedAt: record.createdAt,
    payload,
    metadata: asObject(record.metadata),
  };
}

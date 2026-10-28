import type {
  AnalysisListResponse,
  AnalysisProgress,
  AnalysisResult,
  AnalysisStatus,
  Beat,
  DeviceInfo,
  DeviceVendor,
  EngineStatus,
  HealthRecord,
  ImportPreview,
  ImportRequires,
  Measurement,
  Quality,
  QualitySegment,
  QualityWarning,
  RecordStatus,
  RecordSummary,
  SourceInfo,
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
  let status: RecordStatus;
  if (analysisStatus) {
    status = analysisStatus;
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
    isDemo:
      record.metadata?.demo === true || record.metadata?.mock === true,
    notes: record.notes ?? "",
    signalCount,
    qualityScore: record.quality?.score ?? null,
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

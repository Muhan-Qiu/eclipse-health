import { ApiError } from "./error";
import type { ApiClient, PreviewSource, RecordListParams } from "./contract";
import type {
  AnalysisListResponse,
  AnalysisResult,
  AnalysisStartBody,
  AnalysisStartResponse,
  Beat,
  EngineStatus,
  HealthRecord,
  HealthStatus,
  ImportCommitBody,
  ImportCommitResponse,
  ImportHintFormat,
  ImportPreview,
  Measurement,
  Member,
  Quality,
  RecordPage,
  SignalData,
  SignalMetadata,
  SourceInfo,
} from "./types";

/* ------------------------------------------------------------------ *
 * 演示数据：只在 VITE_USE_MOCK=true 时使用。
 * 波形为确定性合成信号，不含任何真实患者数据，也不构成诊断。
 * ------------------------------------------------------------------ */

const MEMBER_ID = "mem_0193a4c2-7b1e-7c3a-9d20-000000000001";
const DEMO_MODEL = "cardia-2.0";

function sleep<T>(value: T, ms = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function uid(prefix: string): string {
  const stamp = Date.now().toString(16).padStart(12, "0");
  const random = Math.random().toString(16).slice(2, 10);
  return `${prefix}_${stamp}-${random}`;
}

function hashOf(text: string): string {
  let state = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    state ^= text.charCodeAt(index);
    state = Math.imul(state, 16777619);
  }
  const chunk = (state >>> 0).toString(16).padStart(8, "0");
  return `sha256:${chunk.repeat(8)}`;
}

function gaussian(t: number, center: number, sigma: number, amplitude: number) {
  const d = t - center;
  return amplitude * Math.exp(-(d * d) / (2 * sigma * sigma));
}

interface SyntheticEcg {
  samples: Float32Array;
  rPeaks: number[];
  labels: string[];
}

/** 生成可复现的 PQRST 波形；每 11 搏插入一个宽 QRS（VEB），每 17 搏一个 SVEB。 */
function synthesizeEcg(
  fs: number,
  durationSec: number,
  options: { ver?: boolean } = {},
): SyntheticEcg {
  const count = Math.round(fs * durationSec);
  const samples = new Float32Array(count);
  const rPeaks: number[] = [];
  const labels: string[] = [];
  const period = 0.8;

  for (let index = 0; index < count; index += 1) {
    const t = index / fs;
    let value =
      0.02 * Math.sin(2 * Math.PI * 0.23 * t) +
      0.007 * Math.sin(2 * Math.PI * 13 * t) +
      0.004 * Math.sin(2 * Math.PI * 37 * t);

    const beatIndex = Math.floor(t / period);
    const phase = t - beatIndex * period - 0.15;
    const isVeb = options.ver !== false && beatIndex % 11 === 7;
    const isSveb = options.ver !== false && beatIndex % 17 === 12;

    if (phase >= -0.2 && phase < 0.8) {
      if (isVeb) {
        value +=
          gaussian(phase, 0.02, 0.028, -0.1) +
          gaussian(phase, 0.27, 0.03, 1.15) +
          gaussian(phase, 0.31, 0.03, -0.55) +
          gaussian(phase, 0.46, 0.08, -0.3);
      } else {
        const scale = isSveb ? 0.92 : 1;
        value +=
          gaussian(phase, 0.0, 0.026, 0.08 * scale) +
          gaussian(phase, 0.085, 0.008, -0.12 * scale) +
          gaussian(phase, 0.105, 0.009, 1.0 * scale) +
          gaussian(phase, 0.125, 0.012, -0.24 * scale) +
          gaussian(phase, 0.32, 0.055, 0.26 * scale);
      }
    }

    samples[index] = value;
    const peakSample = Math.round((beatIndex * period + 0.15 + 0.105) * fs);
    if (peakSample === index) {
      rPeaks.push(index);
      labels.push(isVeb ? "VEB" : isSveb ? "SVEB" : "N");
    }
  }

  return { samples, rPeaks, labels };
}

function makeQuality(): Quality {
  return {
    score: 0.93,
    level: "good",
    warnings: [
      {
        code: "noise_segment",
        severity: "warning",
        startSec: 7.4,
        endSec: 8.1,
        message: "该区段基线漂移与肌电噪声偏高",
      },
    ],
    segments: [
      { startSec: 0, endSec: 7.4, quality: 0.95 },
      { startSec: 7.4, endSec: 8.1, quality: 0.62 },
      { startSec: 8.1, endSec: 12, quality: 0.94 },
    ],
  };
}

function buildMeasurements(
  recordId: string,
  analysisId: string,
  durationSec: number,
  qualityScore: number,
  ratios: Record<string, number>,
): Measurement[] {
  const common = {
    recordId,
    analysisId,
    range: { startSec: 0, endSec: durationSec },
    confidence: qualityScore,
    method: `${DEMO_MODEL}/demo`,
    warnings: [],
  };
  const measurement = (
    code: string,
    label: string,
    value: number | null,
    unit: string,
    ucum: string,
    extra: Partial<Measurement> = {},
  ): Measurement => ({
    schema: "org.eclipsehealth.measurement/1",
    id: uid("msr"),
    code,
    label,
    value,
    unit,
    ucum,
    ...common,
    ...extra,
  });

  return [
    measurement("heart_rate_mean", "平均心率", 75, "bpm", "/min"),
    measurement("heart_rate_min", "最小心率", 68, "bpm", "/min"),
    measurement("heart_rate_max", "最大心率", 83, "bpm", "/min"),
    measurement("rr_mean", "平均 RR", 800, "ms", "ms"),
    measurement("sdnn", "SDNN", 45, "ms", "ms"),
    measurement("rmssd", "RMSSD", 38, "ms", "ms"),
    measurement("pnn50", "pNN50", 14.2, "%", "%"),
    measurement("qrs_duration", "QRS 时程", null, "ms", "ms", {
      method: "unavailable",
      warnings: [{ code: "delineation_not_implemented", severity: "info" }],
    }),
    measurement("pr_interval", "PR 间期", null, "ms", "ms", {
      method: "unavailable",
      warnings: [{ code: "delineation_not_implemented", severity: "info" }],
    }),
    measurement("qt_interval", "QT 间期", null, "ms", "ms", {
      method: "unavailable",
      warnings: [{ code: "delineation_not_implemented", severity: "info" }],
    }),
    measurement("qtc", "QTc", null, "ms", "ms", {
      method: "unavailable",
      warnings: [{ code: "delineation_not_implemented", severity: "info" }],
    }),
    measurement("n_ratio", "N 比例", ratios.N ?? 93.3, "%", "%"),
    measurement("svb_ratio", "SVEB 比例", ratios.SVEB ?? 0.7, "%", "%"),
    measurement("veb_ratio", "VEB 比例", ratios.VEB ?? 6.0, "%", "%"),
    measurement("f_ratio", "F 比例", ratios.F ?? 0, "%", "%"),
  ];
}

function buildAnalysis(
  record: HealthRecord,
  lead: string,
  synth: SyntheticEcg,
): AnalysisResult {
  const analysisId = uid("ana");
  const total = Math.max(synth.rPeaks.length, 1);
  const counts = { N: 0, SVEB: 0, VEB: 0, F: 0 } as Record<string, number>;
  for (const label of synth.labels) counts[label] = (counts[label] ?? 0) + 1;
  const ratios = {
    N: (counts.N / total) * 100,
    SVEB: (counts.SVEB / total) * 100,
    VEB: (counts.VEB / total) * 100,
    F: (counts.F / total) * 100,
  };

  const beats: Beat[] = synth.rPeaks.map((peak, index) => {
    const label = synth.labels[index] ?? "N";
    const probabilities =
      label === "VEB"
        ? { N: 0.02, SVEB: 0.03, VEB: 0.94, F: 0.01 }
        : label === "SVEB"
          ? { N: 0.08, SVEB: 0.86, VEB: 0.05, F: 0.01 }
          : { N: 0.985, SVEB: 0.006, VEB: 0.007, F: 0.002 };
    const previous = index > 0 ? synth.rPeaks[index - 1] : peak;
    return {
      index,
      rPeakSample: peak,
      label,
      confidence: label === "N" ? 0.985 : 0.94,
      rrPrevMs: index > 0 ? Math.round(((peak - previous) / record.samplingRate!) * 1000) : null,
      probabilities,
    };
  });

  const startedAt = new Date(Date.now() - 1_820).toISOString();
  const completedAt = new Date(Date.now() - 980).toISOString();
  const summary = `平均心率 75 bpm · N ${ratios.N.toFixed(1)}% · SVEB ${ratios.SVEB.toFixed(1)}% · VEB ${ratios.VEB.toFixed(1)}% · F ${ratios.F.toFixed(1)}%`;

  return {
    schema: "org.eclipsehealth.analysis/1",
    id: analysisId,
    recordId: record.id,
    moduleId: "org.eclipsehealth.cardia",
    modelId: DEMO_MODEL,
    modelVersion: "2.0.0",
    task: "beat-classification",
    status: "completed",
    startedAt,
    completedAt,
    durationMs: 840,
    summary,
    quality: makeQuality(),
    measurements: buildMeasurements(
      record.id,
      analysisId,
      record.durationSec ?? 12,
      0.93,
      ratios,
    ),
    beats,
    annotations: [],
    warnings: [
      {
        code: "demo_data",
        severity: "info",
        message: "示例分析结果，用于界面演示，不能用于诊断",
      },
    ],
    parameters: {
      engine: "cardia",
      engineVersion: "demo",
      sequenceLength: 64,
      classOrder: ["N", "SVEB", "VEB", "F"],
      meanConfidence: 0.94,
      lead,
      originalFs: record.samplingRate,
      resampled: false,
      allowShortRecord: true,
    },
    provenance: {
      preprocess: "cardia-v2",
      preprocessVersion: "2.0",
      modelFile: "cardia.onnx",
      engine: "eclipse-health-backend/analysis@demo",
    },
    progress: null,
    error: null,
  };
}

const signalStore = new Map<string, { lead: string; fs: number; unit: string; samples: Float32Array }[]>();
const analysisStore = new Map<string, AnalysisResult[]>();
const records: HealthRecord[] = [];

function registerSignal(
  recordId: string,
  lead: string,
  fs: number,
  samples: Float32Array,
  unit = "mV",
): string {
  const list = signalStore.get(recordId) ?? [];
  list.push({ lead, fs, unit, samples });
  signalStore.set(recordId, list);
  return `sig_${recordId.replace(/^rec_/, "")}-${list.length}`;
}

function makeRecord(input: {
  id: string;
  capturedAt: string;
  source: SourceInfo;
  moduleId: string;
  fs: number;
  lead: string;
  durationSec: number;
  tags: string[];
  notes?: string;
  samples: Float32Array;
  withAnalysis?: boolean;
}): HealthRecord {
  const signalId = registerSignal(input.id, input.lead, input.fs, input.samples);
  const record: HealthRecord = {
    schema: "org.eclipsehealth.record/1",
    id: input.id,
    memberId: MEMBER_ID,
    recordType: "org.eclipsehealth.ecg",
    moduleId: input.moduleId,
    capturedAt: input.capturedAt,
    timezone: "Asia/Shanghai",
    source: input.source,
    samplingRate: input.fs,
    leads: [input.lead],
    durationSec: input.durationSec,
    unit: "mV",
    signalIds: [signalId],
    quality: null,
    tags: input.tags,
    notes: input.notes ?? "",
    metadata: { demo: true, lead: input.lead },
    payload: {},
    provenance: { adapterVersion: "demo" },
    createdAt: input.capturedAt,
    updatedAt: input.capturedAt,
    deletedAt: null,
  };
  records.push(record);
  if (input.withAnalysis) {
    const synth = synthesizeEcg(input.fs, input.durationSec);
    const analysis = buildAnalysis(record, input.lead, synth);
    analysisStore.set(record.id, [analysis]);
    record.quality = analysis.quality;
  }
  return record;
}

function seedDemoData() {
  const now = Date.now();
  const apple = synthesizeEcg(360, 12);
  makeRecord({
    id: "rec_0193a4c2-7b1e-7c3a-9d20-1a2b3c4d5e60",
    capturedAt: new Date(now - 2 * 86_400_000).toISOString(),
    source: { kind: "wearable", manufacturer: "Apple", device: "Watch Series 9", app: "Health" },
    moduleId: "org.eclipsehealth.apple",
    fs: 360,
    lead: "MLII",
    durationSec: 12,
    tags: ["morning", "resting"],
    notes: "示例：晨起静息记录",
    samples: apple.samples,
    withAnalysis: true,
  });

  const samsung = synthesizeEcg(360, 11);
  makeRecord({
    id: "rec_0193a0d1-2f7a-7b51-a6c8-9d0e1f2a3b4c",
    capturedAt: new Date(now - 6 * 86_400_000).toISOString(),
    source: { kind: "wearable", manufacturer: "Samsung", device: "Galaxy Watch7", app: "Samsung Health" },
    moduleId: "org.eclipsehealth.samsung",
    fs: 360,
    lead: "I",
    durationSec: 11,
    tags: ["postExercise", "evening"],
    notes: "示例：运动后记录",
    samples: samsung.samples,
    withAnalysis: true,
  });

  const huawei = synthesizeEcg(500, 10);
  makeRecord({
    id: "rec_01939c8e-6d2b-7330-bf4e-5a6b7c8d9e0f",
    capturedAt: new Date(now - 12 * 86_400_000).toISOString(),
    source: { kind: "wearable", manufacturer: "Huawei", device: "WATCH GT 5 Pro", app: "华为运动健康" },
    moduleId: "org.eclipsehealth.huawei",
    fs: 500,
    lead: "I",
    durationSec: 10,
    tags: ["morning"],
    notes: "示例：尚未分析",
    samples: huawei.samples,
    withAnalysis: false,
  });
}
seedDemoData();

function activeRecords(): HealthRecord[] {
  return records.filter((record) => !record.deletedAt);
}

function sortByCapturedAt(list: HealthRecord[]): HealthRecord[] {
  return [...list].sort(
    (a, b) => new Date(b.capturedAt).getTime() - new Date(a.capturedAt).getTime(),
  );
}

function listRecords(params: RecordListParams = {}): RecordPage {
  const limit = params.limit ?? 20;
  const offset = params.offset ?? 0;
  let filtered = sortByCapturedAt(activeRecords());
  if (params.capturedFrom) {
    const from = new Date(params.capturedFrom).getTime();
    filtered = filtered.filter((record) => new Date(record.capturedAt).getTime() >= from);
  }
  if (params.capturedTo) {
    const to = new Date(params.capturedTo).getTime();
    filtered = filtered.filter((record) => new Date(record.capturedAt).getTime() <= to);
  }
  if (params.recordType) {
    filtered = filtered.filter((record) => record.recordType === params.recordType);
  }
  if (params.moduleId) {
    filtered = filtered.filter((record) => record.moduleId === params.moduleId);
  }
  return {
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    limit,
    offset,
  };
}

function findRecord(id: string): HealthRecord {
  const record = activeRecords().find((item) => item.id === id);
  if (!record) throw new ApiError("记录不存在", { status: 404, code: "record_not_found" });
  return record;
}

function signalMetadata(recordId: string): SignalMetadata[] {
  const list = signalStore.get(recordId) ?? [];
  return list.map((signal, index) => ({
    schema: "org.eclipsehealth.signal/1",
    id: `sig_${recordId.replace(/^rec_/, "")}-${index + 1}`,
    recordId,
    lead: signal.lead,
    fs: signal.fs,
    unit: signal.unit,
    dtype: "float32",
    shape: [signal.samples.length],
    startSample: 0,
    storage: {
      kind: "file",
      relativePath: `signals/${recordId}.f32`,
      sha256: hashOf(`${recordId}-${signal.lead}`).replace("sha256:", ""),
      byteOrder: "little",
    },
    createdAt: new Date().toISOString(),
  }));
}

function getAnalysisList(recordId: string): AnalysisListResponse {
  const completed = analysisStore.get(recordId) ?? [];
  const running: AnalysisResult[] = [];
  for (const run of runningAnalyses.values()) {
    if (run.record.id === recordId) running.push(materializeRun(run));
  }
  return { items: [...running, ...completed] };
}

interface RunningAnalysis {
  id: string;
  record: HealthRecord;
  lead: string;
  synth: SyntheticEcg;
  createdAt: number;
}

const runningAnalyses = new Map<string, RunningAnalysis>();

function materializeRun(run: RunningAnalysis): AnalysisResult {
  const elapsed = Date.now() - run.createdAt;
  const base = buildAnalysis(run.record, run.lead, run.synth);
  base.id = run.id;
  base.startedAt = new Date(run.createdAt).toISOString();
  base.completedAt = null;
  base.durationMs = null;

  if (elapsed < 600) {
    return {
      ...base,
      status: "queued",
      beats: [],
      measurements: [],
      summary: "",
      quality: { score: null, level: null, warnings: [], segments: [] },
      progress: { stage: "quality", percent: 5 },
    };
  }
  if (elapsed < 1_300) {
    return {
      ...base,
      status: "running",
      beats: [],
      measurements: [],
      summary: "",
      progress: { stage: "features", percent: 40 },
    };
  }
  if (elapsed < 2_000) {
    return {
      ...base,
      status: "running",
      progress: { stage: "inference", percent: 72 },
    };
  }
  return {
    ...base,
    status: "completed",
    completedAt: new Date(run.createdAt + 2_000).toISOString(),
    durationMs: 2_000,
    progress: null,
  };
}

function persistCompleted(analysis: AnalysisResult): void {
  const list = analysisStore.get(analysis.recordId) ?? [];
  if (list.some((item) => item.id === analysis.id)) return;
  analysisStore.set(analysis.recordId, [
    { ...analysis, status: "completed" },
    ...list,
  ]);
}

interface MockImport {
  preview: ImportPreview;
  durationSec: number;
  samples: Float32Array;
  fs: number;
  lead: string;
  sourceName: string;
}

const imports = new Map<string, MockImport>();
let importCounter = 0;
let commitCounter = 0;

const SUPPORTED_EXT = new Set(["zip", "hea", "csv", "txt"]);

function extensionOf(name: string): string {
  const parts = name.toLowerCase().split(".");
  return parts.length > 1 ? parts[parts.length - 1] : "";
}

function previewImport(
  source: PreviewSource,
  hintFormat: ImportHintFormat = "auto",
): ImportPreview {
  const name = source.file?.name ?? source.path?.split(/[\\/]/).pop() ?? "record";
  const ext = extensionOf(name);
  const size = source.file?.size ?? 1_024;
  if (name === "record" || (!SUPPORTED_EXT.has(ext) && hintFormat === "auto")) {
    throw new ApiError("无法识别的文件格式，请提供 WFDB 压缩包或 CSV", {
      status: 422,
      code: "unsupported_format",
      details: { fileNameHash: hashOf(name) },
    });
  }
  if (size > 200 * 1024 * 1024) {
    throw new ApiError("文件超过 200MB 限制", { status: 413, code: "file_too_large" });
  }

  const format = hintFormat !== "auto" ? hintFormat : ext === "hea" || ext === "zip" ? "wfdb" : "csv";
  const fs = format === "wfdb" ? 360 : 500;
  const durationSec = 10;
  const synth = synthesizeEcg(fs, durationSec);
  const lead = format === "wfdb" ? "MLII" : "I";
  importCounter += 1;
  const importId = `imp_mock_${String(importCounter).padStart(4, "0")}`;
  const requiresLead = format === "csv" && !/lead|ecg|mlii|ii/i.test(name);

  const preview: ImportPreview = {
    importId,
    format,
    adapterId: format === "wfdb" ? "org.eclipsehealth.wfdb" : "org.eclipsehealth.csv",
    fileNameHash: hashOf(name),
    fileHash: hashOf(`${name}:${size}`),
    samplingRate: fs,
    leads: [lead],
    durationSec,
    unit: "mV",
    requires: { samplingRate: false, lead: requiresLead, unit: false },
    warnings:
      format === "wfdb"
        ? [
            {
              code: "reference_annotations",
              severity: "info",
              message: "检测到参考 R 峰标注，仅用于对照，不作为诊断标签",
            },
          ]
        : [],
    preview: { nSamples: synth.samples.length, samples: Array.from(synth.samples.slice(0, 2000)) },
    hasAnnotations: format === "wfdb",
    annotationCount: format === "wfdb" ? synth.rPeaks.length : 0,
  };

  imports.set(importId, {
    preview,
    durationSec,
    samples: synth.samples,
    fs,
    lead,
    sourceName: name,
  });
  return preview;
}

function commitImport(
  importId: string,
  body: ImportCommitBody,
): ImportCommitResponse {
  const pending = imports.get(importId);
  if (!pending) {
    throw new ApiError("导入会话不存在或已过期", {
      status: 404,
      code: "import_not_found",
    });
  }
  const parameters = body.parameters ?? {};
  const fs = parameters.samplingRate ?? pending.fs;
  if (!Number.isFinite(fs) || fs <= 0) {
    throw new ApiError("采样率必须为正数", { status: 422, code: "invalid_sampling_rate" });
  }
  const lead = parameters.lead?.trim() || pending.lead;
  const inverted = parameters.polarity === "inverted";
  const samples = inverted
    ? Float32Array.from(pending.samples, (value) => -value)
    : pending.samples;
  const durationSec = samples.length / fs;

  commitCounter += 1;
  const capturedAt = body.capturedAt || new Date().toISOString();
  const record: HealthRecord = {
    schema: "org.eclipsehealth.record/1",
    id: uid("rec"),
    memberId: body.memberId || MEMBER_ID,
    recordType: "org.eclipsehealth.ecg",
    moduleId: pending.preview.adapterId,
    capturedAt,
    timezone: body.timezone || "Asia/Shanghai",
    source: { kind: "import", device: pending.preview.format.toUpperCase() },
    samplingRate: fs,
    leads: [lead],
    durationSec,
    unit: parameters.unit || pending.preview.unit,
    signalIds: [],
    quality: null,
    tags: body.tags ?? [],
    notes: body.notes ?? "",
    metadata: {
      demo: true,
      lead,
      polarity: inverted ? "inverted" : "normal",
      importCount: commitCounter,
    },
    payload: {},
    provenance: {
      fileNameHash: pending.preview.fileNameHash,
      fileHash: pending.preview.fileHash,
      adapterVersion: "demo",
    },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    deletedAt: null,
  };
  record.signalIds = [registerSignal(record.id, lead, fs, samples)];
  records.push(record);
  imports.delete(importId);
  return { recordId: record.id, record };
}

const mockApi: ApiClient = {
  health: () =>
    sleep<HealthStatus>({ status: "ok", version: "0.1.0-demo", mock: true }),

  members: {
    list: () =>
      sleep<Member[]>([
        {
          schema: "org.eclipsehealth.member/1",
          id: MEMBER_ID,
          displayName: "本人",
          sex: "unknown",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ]),
  },

  records: {
    list: (params) => sleep(listRecords(params)),
    get: (id) => sleep(findRecord(id)),
    delete: async (id) => {
      const record = findRecord(id);
      const now = new Date().toISOString();
      record.deletedAt = now;
      record.updatedAt = now;
      await sleep(undefined);
    },
    signals: (id) => {
      findRecord(id);
      return sleep(signalMetadata(id));
    },
    signal: (id, lead): Promise<SignalData> => {
      findRecord(id);
      const list = signalStore.get(id) ?? [];
      const signal = lead ? list.find((item) => item.lead === lead) : list[0];
      if (!signal) {
        return Promise.reject(
          new ApiError("记录没有波形", { status: 404, code: "signal_not_found" }),
        );
      }
      return sleep({
        recordId: id,
        lead: signal.lead,
        fs: signal.fs,
        unit: signal.unit,
        samples: signal.samples,
        sampleCount: signal.samples.length,
      });
    },
    analyses: (id) => {
      findRecord(id);
      return sleep(getAnalysisList(id));
    },
    startAnalysis: async (
      id: string,
      body: AnalysisStartBody = {},
    ): Promise<AnalysisStartResponse> => {
      const record = findRecord(id);
      const leads = signalStore.get(id) ?? [];
      if (leads.length === 0) {
        throw new ApiError("记录没有可分析的波形", {
          status: 409,
          code: "record_has_no_signal",
        });
      }
      const allowShort = Boolean(body.options?.allowShortRecord);
      if ((record.durationSec ?? 0) < 60 && !allowShort) {
        throw new ApiError("记录过短，需要显式允许短记录", {
          status: 422,
          code: "too_few_beats",
        });
      }
      const synth = synthesizeEcg(leads[0].fs, record.durationSec ?? 12);
      const run: RunningAnalysis = {
        id: uid("ana"),
        record,
        lead: leads[0].lead,
        synth,
        createdAt: Date.now(),
      };
      runningAnalyses.set(run.id, run);
      setTimeout(() => {
        const materialized = materializeRun(run);
        if (materialized.status === "completed") persistCompleted(materialized);
        runningAnalyses.delete(run.id);
      }, 2_100);
      return sleep({
        analysisId: run.id,
        recordId: id,
        status: "queued",
        engine: "cardia",
      });
    },
  },

  analyses: {
    get: async (id, includeBeats = true) => {
      const run = runningAnalyses.get(id);
      if (run) {
        const materialized = materializeRun(run);
        if (materialized.status === "completed") {
          persistCompleted(materialized);
          runningAnalyses.delete(id);
        }
        if (!includeBeats) return { ...materialized, beats: [] };
        return sleep(materialized, 120);
      }
      for (const list of analysisStore.values()) {
        const found = list.find((analysis) => analysis.id === id);
        if (found) return sleep(includeBeats ? found : { ...found, beats: [] }, 120);
      }
      throw new ApiError("分析不存在", { status: 404, code: "analysis_not_found" });
    },
  },

  engine: {
    status: () =>
      sleep<EngineStatus>({
        status: "ready",
        engine: "cardia",
        moduleId: "org.eclipsehealth.cardia",
        modelId: DEMO_MODEL,
        modelVersion: "2.0.0",
        message: "示例引擎已就绪",
        startedAt: new Date(Date.now() - 60_000).toISOString(),
        readyAt: new Date(Date.now() - 58_000).toISOString(),
      }),
  },

  imports: {
    preview: (source, hintFormat) => sleep(previewImport(source, hintFormat), 320),
    commit: (importId, body) => sleep(commitImport(importId, body), 320),
    discard: async (importId) => {
      imports.delete(importId);
      await sleep(undefined);
    },
  },
};

export { mockApi };

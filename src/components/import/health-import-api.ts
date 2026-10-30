/**
 * 健康数据包（Apple / 小米）的预览与提交。
 *
 * 共享的 `api.imports.*` 客户端只保留波形导入所需的字段；这里直接读取
 * 后端的 recordCounts / created / skipped / failed，供导入对话框显示计数。
 */

import { api, apiMode, baseUrl, ApiError } from "@/lib/api/client";
import type {
  HealthRecord,
  ImportCommitBody,
  ImportPreview,
  ImportWarning,
} from "@/lib/api/types";

export type ImportSourceKind = "auto" | "apple-health" | "xiaomi";

export interface ImportRecordCounts {
  steps: number;
  heartRate: number;
  sleep: number;
  bodyMass: number;
  bloodPressure: number;
  ecg: number;
}

export interface HealthImportPreview extends ImportPreview {
  recordCounts: ImportRecordCounts;
  totalRecords: number;
}

export interface HealthImportCommitResult {
  recordId: string;
  record: HealthRecord | null;
  created: number;
  skipped: number;
  failed: number;
  duplicateFile: boolean;
  recordCounts: ImportRecordCounts;
}

const IMPORT_TIMEOUT_MS = 180_000;

const EMPTY_COUNTS: ImportRecordCounts = {
  steps: 0,
  heartRate: 0,
  sleep: 0,
  bodyMass: 0,
  bloodPressure: 0,
  ecg: 0,
};

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNum(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function bool(value: unknown): boolean {
  return value === true;
}

function counts(value: unknown): ImportRecordCounts {
  const item = asRecord(value);
  return {
    steps: num(item.steps),
    heartRate: num(item.heartRate),
    sleep: num(item.sleep),
    bodyMass: num(item.bodyMass),
    bloodPressure: num(item.bloodPressure),
    ecg: num(item.ecg),
  };
}

function warnings(value: unknown): ImportWarning[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => {
    const item = asRecord(entry);
    const severity = str(item.severity, "info");
    return {
      code: str(item.code, "unknown"),
      severity:
        severity === "warning" || severity === "error" ? severity : "info",
      message: str(item.message),
      startSec: nullableNum(item.startSec),
      endSec: nullableNum(item.endSec),
    };
  });
}

async function requestJson(
  path: string,
  init: RequestInit,
  timeoutMs = IMPORT_TIMEOUT_MS,
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时，请检查后端是否正在运行", {
        code: "timeout",
        cause: error,
      });
    }
    throw new ApiError("无法连接到本地后端", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = `请求失败（${response.status}）`;
    try {
      const body = asRecord(await response.json());
      if (typeof body.code === "string") code = body.code;
      if (typeof body.message === "string") message = body.message;
    } catch {
      // 非 JSON 错误体保留通用文案
    }
    throw new ApiError(message, { status: response.status, code });
  }
  return response.json();
}

function normalizePreview(value: unknown): HealthImportPreview {
  const item = asRecord(value);
  const preview = asRecord(item.preview);
  const requires = asRecord(item.requires);
  const rawSamples = Array.isArray(preview.samples) ? preview.samples : [];
  const leads = Array.isArray(item.leads)
    ? item.leads.filter((lead): lead is string => typeof lead === "string")
    : [];
  return {
    importId: str(item.importId),
    format: str(item.format, "unknown"),
    adapterId: str(item.adapterId),
    fileNameHash: str(item.fileNameHash) || undefined,
    fileHash: str(item.fileHash) || undefined,
    samplingRate: nullableNum(item.samplingRate),
    leads,
    durationSec: nullableNum(item.durationSec),
    unit: str(item.unit, "mV"),
    requires: {
      samplingRate: bool(requires.samplingRate),
      lead: bool(requires.lead),
      unit: bool(requires.unit),
    },
    warnings: warnings(item.warnings),
    preview: {
      nSamples: num(preview.nSamples, rawSamples.length),
      samples: rawSamples.map((sample) => num(sample)),
    },
    hasAnnotations: bool(item.hasAnnotations),
    annotationCount: num(item.annotationCount),
    recordCounts: counts(item.recordCounts),
    totalRecords: num(item.totalRecords),
  };
}

export async function previewHealthImport(
  file: File,
  source: ImportSourceKind,
): Promise<HealthImportPreview> {
  if (apiMode.mock) {
    const preview = await api.imports.preview({ file });
    return { ...preview, recordCounts: { ...EMPTY_COUNTS }, totalRecords: 0 };
  }
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("hintFormat", source);
  const value = await requestJson("/imports/preview", {
    method: "POST",
    body: form,
  });
  return normalizePreview(value);
}

export async function commitHealthImport(
  importId: string,
  body: ImportCommitBody,
): Promise<HealthImportCommitResult> {
  if (apiMode.mock) {
    const result = await api.imports.commit(importId, body);
    return {
      recordId: result.recordId,
      record: result.record,
      created: 1,
      skipped: 0,
      failed: 0,
      duplicateFile: false,
      recordCounts: { ...EMPTY_COUNTS },
    };
  }
  const value = await requestJson(
    `/imports/${encodeURIComponent(importId)}/commit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  const item = asRecord(value);
  return {
    recordId: str(item.recordId),
    record: (item.record ?? null) as HealthRecord | null,
    created: num(item.created, 1),
    skipped: num(item.skipped),
    failed: num(item.failed),
    duplicateFile: bool(item.duplicateFile),
    recordCounts: counts(item.recordCounts),
  };
}

export const COUNT_ORDER = [
  "steps",
  "heartRate",
  "sleep",
  "bodyMass",
  "bloodPressure",
  "ecg",
] as const;

export type CountKey = (typeof COUNT_ORDER)[number];

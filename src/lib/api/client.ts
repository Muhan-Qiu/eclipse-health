import { ApiError } from "./error";
import { mockApi } from "./mock";
import type { ApiClient, PreviewSource, RecordListParams } from "./contract";
import type {
  AnalysisListResponse,
  AnalysisResult,
  AnalysisStartBody,
  AnalysisStartResponse,
  EngineStatus,
  HealthRecord,
  HealthStatus,
  ImportCommitBody,
  ImportCommitResponse,
  ImportHintFormat,
  ImportPreview,
  Member,
  RecordPage,
  SignalData,
  SignalMetadata,
} from "./types";
import {
  normalizeAnalysis,
  normalizeAnalysisList,
  normalizeEngine,
  normalizeImportPreview,
} from "./adapters";

const DEFAULT_BASE_URL = "http://127.0.0.1:8765/api/v1";

export const baseUrl = (
  import.meta.env.VITE_API_BASE ||
  import.meta.env.VITE_API_BASE_URL ||
  DEFAULT_BASE_URL
).replace(/\/+$/, "");

/**
 * 默认走真实 API。只有显式 `VITE_USE_MOCK=true` 才启用演示数据，
 * 这样生产构建不会把真实数据静默替换成示例。
 */
export const useMock = import.meta.env.VITE_USE_MOCK === "true";

export { ApiError };

const DEFAULT_TIMEOUT_MS = 15_000;
const BINARY_TIMEOUT_MS = 60_000;
const IMPORT_TIMEOUT_MS = 180_000;

async function fetchWithTimeout(
  path: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${baseUrl}${path}`, {
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
}

async function responseError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = `请求失败（${response.status}）`;
  let details: unknown;
  try {
    const body = (await response.json()) as Record<string, unknown>;
    if (typeof body.code === "string") code = body.code;
    if (typeof body.message === "string") message = body.message;
    details = body.details;
  } catch {
    // 非 JSON 错误体（代理/网关）保留通用文案
  }
  return new ApiError(message, { status: response.status, code, details });
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const response = await fetchWithTimeout(
    path,
    {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
    },
    timeoutMs,
  );
  if (!response.ok) throw await responseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestBinary(
  path: string,
): Promise<{ buffer: ArrayBuffer; headers: Headers }> {
  const response = await fetchWithTimeout(
    path,
    { headers: { Accept: "application/octet-stream" } },
    BINARY_TIMEOUT_MS,
  );
  if (!response.ok) throw await responseError(response);
  return { buffer: await response.arrayBuffer(), headers: response.headers };
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function decodeFloat32LittleEndian(buffer: ArrayBuffer): Float32Array {
  const count = Math.floor(buffer.byteLength / 4);
  const view = new DataView(buffer);
  const samples = new Float32Array(count);
  for (let index = 0; index < count; index += 1) {
    samples[index] = view.getFloat32(index * 4, true);
  }
  return samples;
}

function normalizeSignal(
  buffer: ArrayBuffer,
  headers: Headers,
  recordId: string,
): SignalData {
  const samples = decodeFloat32LittleEndian(buffer);
  return {
    recordId,
    lead: headers.get("X-Signal-Lead") ?? "",
    fs: Number(headers.get("X-Signal-Fs") ?? 0),
    unit: headers.get("X-Signal-Unit") ?? "mV",
    sampleCount: samples.length,
    sha256: headers.get("X-Signal-Sha256") ?? undefined,
    samples,
  };
}

const realApi: ApiClient = {
  health: async (): Promise<HealthStatus> => {
    const body = await requestJson<Record<string, unknown>>("/health");
    return {
      status: typeof body.status === "string" ? body.status : "ok",
      version: typeof body.version === "string" ? body.version : "0.1.0",
      mock: false,
    };
  },

  members: {
    list: () => requestJson<Member[]>("/members"),
  },

  records: {
    list: async (params: RecordListParams = {}): Promise<RecordPage> => {
      const query = buildQuery({
        limit: params.limit,
        offset: params.offset,
        capturedFrom: params.capturedFrom,
        capturedTo: params.capturedTo,
        recordType: params.recordType,
        moduleId: params.moduleId,
      });
      const body = await requestJson<RecordPage | HealthRecord[]>(`/records${query}`);
      if (Array.isArray(body)) {
        return { items: body, total: body.length, limit: params.limit ?? 20, offset: params.offset ?? 0 };
      }
      return {
        items: Array.isArray(body.items) ? body.items : [],
        total: typeof body.total === "number" ? body.total : 0,
        limit: typeof body.limit === "number" ? body.limit : params.limit ?? 20,
        offset: typeof body.offset === "number" ? body.offset : params.offset ?? 0,
      };
    },

    get: (id) => requestJson<HealthRecord>(`/records/${encodeURIComponent(id)}`),

    delete: async (id) => {
      await requestJson<void>(`/records/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
    },

    signals: (id) =>
      requestJson<SignalMetadata[]>(`/records/${encodeURIComponent(id)}/signals`),

    signal: async (id, lead) => {
      const query = lead ? `?lead=${encodeURIComponent(lead)}` : "";
      const { buffer, headers } = await requestBinary(
        `/records/${encodeURIComponent(id)}/signal${query}`,
      );
      return normalizeSignal(buffer, headers, id);
    },

    analyses: async (id): Promise<AnalysisListResponse> => {
      const body = await requestJson<unknown>(
        `/records/${encodeURIComponent(id)}/analyses`,
      );
      return normalizeAnalysisList(body);
    },

    startAnalysis: async (
      id: string,
      body: AnalysisStartBody = {},
    ): Promise<AnalysisStartResponse> => {
      const raw = await requestJson<Record<string, unknown>>(
        `/records/${encodeURIComponent(id)}/analyses`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            engine: body.engine ?? "cardia",
            options: body.options ?? {},
          }),
        },
        30_000,
      );
      return {
        analysisId: String(raw.analysisId ?? raw.id ?? ""),
        recordId: String(raw.recordId ?? id),
        status: (raw.status as AnalysisStartResponse["status"]) ?? "queued",
        engine: String(raw.engine ?? "cardia"),
      };
    },
  },

  analyses: {
    get: async (id, includeBeats = true): Promise<AnalysisResult> => {
      const body = await requestJson<unknown>(
        `/analyses/${encodeURIComponent(id)}?includeBeats=${includeBeats}`,
      );
      return normalizeAnalysis(body);
    },
  },

  engine: {
    status: async (): Promise<EngineStatus> => {
      try {
        return normalizeEngine(await requestJson<unknown>("/engine"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return normalizeEngine(await requestJson<unknown>("/analysis/engine"));
        }
        throw error;
      }
    },
  },

  imports: {
    preview: async (
      source: PreviewSource,
      hintFormat: ImportHintFormat = "auto",
    ): Promise<ImportPreview> => {
      const form = new FormData();
      if (source.file) form.append("file", source.file, source.file.name);
      if (source.path) form.append("path", source.path);
      form.append("hintFormat", hintFormat);
      const raw = await requestJson<unknown>(
        "/imports/preview",
        { method: "POST", body: form },
        IMPORT_TIMEOUT_MS,
      );
      return normalizeImportPreview(raw);
    },

    commit: async (
      importId: string,
      body: ImportCommitBody,
    ): Promise<ImportCommitResponse> => {
      const raw = await requestJson<Record<string, unknown>>(
        `/imports/${encodeURIComponent(importId)}/commit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        IMPORT_TIMEOUT_MS,
      );
      const record = (raw.record ?? raw) as HealthRecord;
      return {
        recordId: String(raw.recordId ?? record.id ?? ""),
        record,
      };
    },

    discard: async (importId) => {
      try {
        await requestJson<void>(`/imports/${encodeURIComponent(importId)}`, {
          method: "DELETE",
        }, 30_000);
      } catch (error) {
        // 已过 TTL 或已提交的 importId 删除失败不应阻塞用户
        if (!(error instanceof ApiError && error.status === 404)) throw error;
      }
    },
  },
};

export const api: ApiClient = useMock ? mockApi : realApi;

export const apiMode = { mock: useMock, baseUrl } as const;

import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";

export interface StorageCounts {
  members: number;
  records: number;
  signals: number;
  analyses: number;
  measurements: number;
  annotations: number;
  reports: number;
  deletedRecords: number;
}

export interface StorageBytes {
  signals: number;
  reports: number;
  imports: number;
  database: number;
  total: number;
}

export interface StorageInfo {
  dataDir: string;
  counts: StorageCounts;
  bytes: StorageBytes;
  localOnly: boolean;
  telemetry: boolean;
}

export interface PurgeCounts {
  records: number;
  signals: number;
  analyses: number;
  measurements: number;
  annotations: number;
  reports: number;
}

export interface PurgeResult {
  deleted: PurgeCounts;
  removedFiles: Record<string, number>;
}

export interface AppSettings {
  closeToTray: boolean;
  splashEnabled: boolean;
  telemetryEnabled: boolean;
  locale: "zh-CN" | "en-US" | null;
}

export type SettingsPatch = Partial<
  Pick<AppSettings, "closeToTray" | "splashEnabled" | "locale">
>;

export const PURGE_CONFIRM_TOKEN = "DELETE";
export const PURGE_API_TOKEN = "DELETE_ALL";

const TIMEOUT_MS = 30_000;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      headers: { Accept: "application/json", ...init.headers },
      signal: controller.signal,
    });
    if (!response.ok) {
      let code = `http_${response.status}`;
      let message = `请求失败（${response.status}）`;
      let details: unknown;
      try {
        const body = (await response.json()) as Record<string, unknown>;
        if (typeof body.code === "string") code = body.code;
        if (typeof body.message === "string") message = body.message;
        details = body.details;
      } catch {
        // 非 JSON 错误体保留通用文案。
      }
      throw new ApiError(message, { status: response.status, code, details });
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时", { code: "timeout", cause: error });
    }
    throw new ApiError("无法连接本地后端", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }
}

export function fetchStorage(): Promise<StorageInfo> {
  return request<StorageInfo>("/privacy/storage");
}

export function purgeAll(): Promise<PurgeResult> {
  return request<PurgeResult>(
    `/privacy/all?confirm=${encodeURIComponent(PURGE_API_TOKEN)}`,
    { method: "DELETE" },
  );
}

export function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>("/settings");
}

export function updateSettings(patch: SettingsPatch): Promise<AppSettings> {
  return request<AppSettings>("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

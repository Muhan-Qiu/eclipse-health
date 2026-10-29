import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";
import type {
  GenerateReportBody,
  ReportListResponse,
  ReportSummary,
} from "./types";

const REQUEST_TIMEOUT_MS = 180_000;

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
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
      throw new ApiError(message, {
        status: response.status,
        code,
        details,
      });
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("request timed out", { code: "timeout", cause: error });
    }
    throw new ApiError("could not reach the local backend", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }
}

export function generateReport(
  recordId: string,
  body: GenerateReportBody,
): Promise<ReportSummary> {
  return requestJson<ReportSummary>(
    `/records/${encodeURIComponent(recordId)}/reports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function listReports(recordId: string): Promise<ReportListResponse> {
  return requestJson<ReportListResponse>(
    `/records/${encodeURIComponent(recordId)}/reports?limit=100`,
  );
}

export function deleteReport(reportId: string): Promise<void> {
  return requestJson<void>(`/reports/${encodeURIComponent(reportId)}`, {
    method: "DELETE",
  });
}

export const reportHistoryKey = (recordId: string) =>
  ["reports", "history", recordId] as const;

function apiPath(downloadUrl: string): string {
  if (downloadUrl.startsWith("/api/v1/")) return downloadUrl;
  if (downloadUrl.startsWith("/")) return `/api/v1${downloadUrl}`;
  return `/api/v1/${downloadUrl}`;
}

/** 把后端相对下载地址转成浏览器可直接打开的绝对地址。 */
export function reportFileUrl(downloadUrl: string): string {
  if (/^https?:\/\//i.test(downloadUrl)) return downloadUrl;
  return `${new URL(baseUrl).origin}${apiPath(downloadUrl)}`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

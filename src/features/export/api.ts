import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";

export type BackupFormat = "zip" | "json" | "csv";

export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

export interface RestoreCounts {
  records: number;
  signals: number;
  analyses: number;
  measurements: number;
  annotations: number;
  reports: number;
}

export interface RestoreSkipped {
  records: number;
  signals: number;
  analyses: number;
  reports: number;
}

export interface RestoreResult {
  backupVersion: number;
  createdAt: string | null;
  autoBackup: string;
  imported: RestoreCounts;
  skipped: RestoreSkipped;
}

const EXPORT_TIMEOUT_MS = 180_000;
const RESTORE_TIMEOUT_MS = 300_000;
const DIAGNOSTICS_TIMEOUT_MS = 60_000;

async function request(
  path: string,
  init: RequestInit = {},
  timeoutMs = EXPORT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      headers: { Accept: "*/*", ...init.headers },
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
        // 非 JSON 错误体（代理/网关）保留通用文案。
      }
      throw new ApiError(message, { status: response.status, code, details });
    }
    return response;
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

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // 继续尝试普通 filename
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  const value = plain?.[1]?.trim();
  return value || fallback;
}

async function asDownload(response: Response, fallback: string): Promise<DownloadedFile> {
  const blob = await response.blob();
  return {
    blob,
    filename: filenameFromDisposition(
      response.headers.get("Content-Disposition"),
      fallback,
    ),
  };
}

export function downloadBackup(format: BackupFormat): Promise<DownloadedFile> {
  return request(`/export/backup?format=${format}`).then((response) =>
    asDownload(
      response,
      `eclipse-health-backup.${format === "json" ? "json" : format}`,
    ),
  );
}

export function downloadDiagnosticsBundle(): Promise<DownloadedFile> {
  return request("/diagnostics/bundle", {}, DIAGNOSTICS_TIMEOUT_MS).then(
    (response) => asDownload(response, "eclipse-health-diagnostics.zip"),
  );
}

export async function restoreBackup(file: File): Promise<RestoreResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const response = await request(
    "/import/backup",
    { method: "POST", body: form },
    RESTORE_TIMEOUT_MS,
  );
  return (await response.json()) as RestoreResult;
}

export function saveBlob(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

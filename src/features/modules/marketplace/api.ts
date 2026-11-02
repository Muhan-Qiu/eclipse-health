import type { TFunction } from "i18next";
import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";
import type { ModuleState, ModuleSummary } from "../types";
import type {
  MarketplaceIndex,
  MarketplaceInstallBody,
  MarketplaceModule,
  MarketplaceScan,
  MarketplaceSource,
  MarketplaceSources,
  MarketplaceUpdate,
} from "./types";

const INDEX_TIMEOUT_MS = 20_000;
/** 安装包含下载 + 校验 + 写盘，给足时间；仍由 AbortController 兜底。 */
const INSTALL_JOB_TIMEOUT_MS = 30 * 60_000;

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = INDEX_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      headers: { Accept: "application/json", ...init.headers },
      signal: controller.signal,
    });
  } catch (error) {
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
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeScan(value: unknown): MarketplaceScan | undefined {
  const item = asRecord(value);
  const scan: MarketplaceScan = {};
  if (typeof item.status === "string") scan.status = item.status;
  if (typeof item.risk === "string") scan.risk = item.risk;
  if (typeof item.scannedAt === "string") scan.scannedAt = item.scannedAt;
  if (typeof item.reportUrl === "string") scan.reportUrl = item.reportUrl;
  return Object.keys(scan).length > 0 ? scan : undefined;
}

function normalizeModule(value: unknown): MarketplaceModule | null {
  const item = asRecord(value);
  const id = asString(item.id);
  const name = asString(item.name);
  const version = asString(item.version);
  if (!id || !name || !version) return null;
  return {
    id,
    name,
    version,
    type: asString(item.type),
    description: asString(item.description),
    author: asString(item.author),
    license: asString(item.license),
    repository: asString(item.repository) ?? null,
    permissions: asStringArray(item.permissions),
    dependencies: asStringArray(item.dependencies),
    minCoreVersion: asString(item.minCoreVersion),
    categories: asStringArray(item.categories),
    verified: item.verified === true,
    file: asString(item.file),
    size: typeof item.size === "number" ? item.size : undefined,
    sha256: asString(item.sha256),
    scan: normalizeScan(item.scan),
  };
}

export async function getMarketplaceIndex(
  source: MarketplaceSource,
  query = "",
  category = "",
): Promise<MarketplaceIndex> {
  const body = asRecord(
    await requestJson<unknown>(
      `/marketplace/index${buildQuery({
        source,
        q: query,
        category,
      })}`,
    ),
  );
  const modules = Array.isArray(body.modules)
    ? body.modules
        .map(normalizeModule)
        .filter((item): item is MarketplaceModule => item !== null)
    : [];
  return {
    source: body.source === "community" ? "community" : source,
    keyId: asString(body.keyId) ?? null,
    generatedAt: asString(body.generatedAt),
    modules,
  };
}

export async function getMarketplaceUpdates(): Promise<MarketplaceUpdate[]> {
  const body = asRecord(await requestJson<unknown>("/marketplace/updates"));
  // H8 返回 {updates, count}；保留 items 兼容早期契约文档。
  const rawItems = Array.isArray(body.updates)
    ? body.updates
    : Array.isArray(body.items)
      ? body.items
      : [];
  const items: MarketplaceUpdate[] = [];
  for (const raw of rawItems) {
    const item = asRecord(raw);
    const id = asString(item.id) ?? asString(item.moduleId);
    const name = asString(item.name);
    const installedVersion = asString(item.installedVersion);
    const availableVersion =
      asString(item.availableVersion) ?? asString(item.latestVersion);
    if (!id || !name || !installedVersion || !availableVersion) continue;
    const module = normalizeModule({
      ...item,
      id,
      name,
      version: availableVersion,
    });
    if (!module) continue;
    items.push({
      ...module,
      installedVersion,
      availableVersion,
      source: item.source === "community" ? "community" : "official",
    });
  }
  return items;
}

export async function getMarketplaceSources(): Promise<MarketplaceSources> {
  const body = asRecord(
    await requestJson<unknown>("/marketplace/sources"),
  );
  function sourceInfo(value: unknown) {
    const info = asRecord(value);
    return {
      configured: info.configured === true,
      url: asString(info.url) ?? null,
    };
  }
  return {
    official: sourceInfo(body.official),
    community: sourceInfo(body.community),
    keyId:
      asString(body.keyId) ??
      (Array.isArray(body.keyIds) ? asString(body.keyIds[0]) : undefined) ??
      null,
    keyIds: asStringArray(body.keyIds),
  };
}

export async function installMarketplaceModule(
  body: MarketplaceInstallBody,
): Promise<ModuleSummary> {
  // 依赖安装可能在后台跑几分钟（venv + pip），先拿 jobId 再轮询，
  // 避免 300 秒 HTTP 超时被误判为“卡死”。
  const started = asRecord(
    await requestJson<unknown>(
      "/marketplace/install?async=1",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      INDEX_TIMEOUT_MS,
    ),
  );
  const jobId = asString(started.jobId);
  if (!jobId) {
    throw new ApiError("安装任务创建失败", { code: "install_job_missing" });
  }
  const deadline = Date.now() + INSTALL_JOB_TIMEOUT_MS;
  let job: Record<string, unknown> = {};
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    job = asRecord(
      await requestJson<unknown>(`/marketplace/install/${encodeURIComponent(jobId)}`),
    );
    const status = asString(job.status);
    if (status === "done") break;
    if (status === "error") {
      const error = asRecord(job.error);
      throw new ApiError(asString(error.message) ?? "模块安装失败", {
        code: asString(error.code) ?? "module_install_failed",
        details: error.details,
      });
    }
    if (!status) {
      throw new ApiError("安装任务不存在或已过期", { code: "install_job_not_found" });
    }
  }
  if (asString(job.status) !== "done") {
    throw new ApiError("安装超时，请检查网络后重试", { code: "install_timeout" });
  }
  const payload = asRecord(job.result);
  // H8 安装结果是 {source, moduleId, version, ..., module: <模块摘要>}；
  // 兼容直接返回摘要的旧契约。
  const summary = asRecord(payload.module ?? payload);
  return {
    id: asString(summary.id) ?? asString(payload.moduleId) ?? body.moduleId,
    name: asString(summary.name) ?? "",
    description: asString(summary.description) ?? "",
    version: asString(summary.version) ?? asString(payload.version) ?? body.version,
    type: asString(summary.type) ?? "",
    enabled: summary.enabled === true,
    running: summary.running === true,
    state: (asString(summary.state) ?? "installed") as ModuleState,
    requestedPermissions: asStringArray(summary.requestedPermissions),
    grantedPermissions: asStringArray(summary.grantedPermissions),
    previousVersion: asString(summary.previousVersion) ?? null,
    installedAt: asString(summary.installedAt) ?? null,
    updatedAt: asString(summary.updatedAt) ?? null,
  };
}

const ERROR_KEYS: Record<string, string> = {
  marketplace_not_configured: "moduleUi.marketplace.errors.notConfigured",
  marketplace_signature_invalid: "moduleUi.marketplace.errors.signatureInvalid",
  marketplace_fetch_failed: "moduleUi.marketplace.errors.fetchFailed",
  marketplace_index_invalid: "moduleUi.marketplace.errors.indexInvalid",
  marketplace_download_failed: "moduleUi.marketplace.errors.downloadFailed",
  marketplace_download_url_rejected: "moduleUi.marketplace.errors.downloadRejected",
  marketplace_checksum_mismatch: "moduleUi.marketplace.errors.checksum",
  marketplace_module_not_found: "moduleUi.marketplace.errors.notFound",
  marketplace_incompatible_core: "moduleUi.marketplace.errors.incompatibleCore",
  marketplace_resource_exceeded: "moduleUi.marketplace.errors.tooLarge",
  marketplace_source_invalid: "moduleUi.marketplace.errors.sourceInvalid",
  network_error: "moduleUi.errors.network",
  timeout: "moduleUi.errors.timeout",
};

/** 市场错误统一转成可读文案；未知 code 沿用后端 message。 */
export function marketplaceErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const key = ERROR_KEYS[error.code];
    if (key) return t(key);
    if (error.status === 404) return t("moduleUi.marketplace.errors.unavailable");
    return error.message || t("moduleUi.errors.unknown");
  }
  return t("moduleUi.errors.unknown");
}

export function isMarketplaceNotConfigured(error: unknown): boolean {
  return error instanceof ApiError && error.code === "marketplace_not_configured";
}

export const MARKETPLACE_UPDATES_KEY = ["marketplace", "updates"] as const;
export const MARKETPLACE_SOURCES_KEY = ["marketplace", "sources"] as const;
/** 搜索在客户端按网站文案完成，键里不再包含 q。 */
export function marketplaceIndexKey(
  source: MarketplaceSource,
  category: string,
) {
  return ["marketplace", "index", source, category] as const;
}

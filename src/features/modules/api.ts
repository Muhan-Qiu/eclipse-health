import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";
import type {
  AuditEvent,
  AuditPage,
  AuditQuery,
  ContributionKind,
  InstallOptions,
  ModuleContributionGroups,
  ModuleContributionList,
  ModuleManifest,
  ModulePreview,
  ModuleSummary,
  ModuleWidget,
  ModuleWidgetList,
  PermissionsState,
} from "./types";

const DEFAULT_TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 300_000;
/** 首次 RPC 可能要冷启动模块 worker，比普通读接口宽松。 */
const RPC_TIMEOUT_MS = 60_000;

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
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
    throw new ApiError("无法连接本地后端", { code: "network_error", cause: error });
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

export async function listModules(): Promise<ModuleSummary[]> {
  const body = await requestJson<{ modules?: ModuleSummary[] }>("/modules");
  return Array.isArray(body.modules) ? body.modules : [];
}

export function getModuleManifest(moduleId: string): Promise<ModuleManifest> {
  return requestJson<ModuleManifest>(
    `/modules/${encodeURIComponent(moduleId)}/manifest`,
  );
}

export function getPermissions(moduleId: string): Promise<PermissionsState> {
  return requestJson<PermissionsState>(
    `/modules/${encodeURIComponent(moduleId)}/permissions`,
  );
}

export function grantPermission(
  moduleId: string,
  scope: string,
): Promise<PermissionsState> {
  return requestJson<PermissionsState>(
    `/modules/${encodeURIComponent(moduleId)}/permissions/${encodeURIComponent(scope)}`,
    { method: "POST" },
  );
}

export function revokePermission(
  moduleId: string,
  scope: string,
): Promise<PermissionsState> {
  return requestJson<PermissionsState>(
    `/modules/${encodeURIComponent(moduleId)}/permissions/${encodeURIComponent(scope)}`,
    { method: "DELETE" },
  );
}

function lifecycle(moduleId: string, action: string): Promise<ModuleSummary> {
  return requestJson<ModuleSummary>(
    `/modules/${encodeURIComponent(moduleId)}/${action}`,
    { method: "POST" },
  );
}

export const startModule = (moduleId: string) => lifecycle(moduleId, "start");
export const stopModule = (moduleId: string) => lifecycle(moduleId, "stop");
export const enableModule = (moduleId: string) => lifecycle(moduleId, "enable");
export const disableModule = (moduleId: string) => lifecycle(moduleId, "disable");

export async function uninstallModule(
  moduleId: string,
  keepData: boolean,
): Promise<void> {
  await requestJson<unknown>(
    `/modules/${encodeURIComponent(moduleId)}${buildQuery({ keepData: String(keepData) })}`,
    { method: "DELETE" },
  );
}

export function previewModulePackage(file: File): Promise<ModulePreview> {
  const form = new FormData();
  form.append("file", file, file.name);
  return requestJson<ModulePreview>(
    "/modules/preview-upload",
    { method: "POST", body: form },
    UPLOAD_TIMEOUT_MS,
  );
}

export function installModulePackage(
  file: File,
  options: InstallOptions,
): Promise<ModuleSummary> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("enable", options.enable ? "true" : "false");
  if (options.permissions !== null) {
    form.append("permissions", JSON.stringify(options.permissions));
  }
  return requestJson<ModuleSummary>(
    "/modules/install-upload",
    { method: "POST", body: form },
    UPLOAD_TIMEOUT_MS,
  );
}

export async function listAudit(query: AuditQuery = {}): Promise<AuditPage> {  const body = await requestJson<Partial<AuditPage> & { events?: AuditEvent[] }>(
    `/modules/audit${buildQuery({
      moduleId: query.moduleId,
      action: query.action,
      limit: query.limit,
      offset: query.offset,
    })}`,
  );
  const events = Array.isArray(body.events) ? body.events : [];
  return {
    events,
    count: typeof body.count === "number" ? body.count : events.length,
    limit: typeof body.limit === "number" ? body.limit : query.limit ?? 20,
    offset: typeof body.offset === "number" ? body.offset : query.offset ?? 0,
    hasMore: body.hasMore === true,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

function asWidgets(value: unknown): ModuleWidget[] {
  return Array.isArray(value) ? (value as ModuleWidget[]) : [];
}

function asItems(value: unknown): ModuleContributionList["items"] {
  return Array.isArray(value)
    ? (value as ModuleContributionList["items"])
    : [];
}

export function listContributions(): Promise<ModuleContributionGroups>;
export function listContributions(type: "widgets"): Promise<ModuleWidgetList>;
export function listContributions(
  type: Exclude<ContributionKind, "widgets">,
): Promise<ModuleContributionList>;
export async function listContributions(
  type?: ContributionKind,
): Promise<ModuleContributionGroups | ModuleWidgetList | ModuleContributionList> {
  const body = asRecord(
    await requestJson<unknown>(`/modules/contributions${buildQuery({ type })}`),
  );
  if (type === "widgets") {
    return { type, items: asWidgets(body.items) };
  }
  if (type) {
    return { type, items: asItems(body.items) };
  }
  const counts = asRecord(body.counts);
  return {
    widgets: asWidgets(body.widgets),
    pages: asItems(body.pages),
    tools: asItems(body.tools),
    recordTypes: asItems(body.recordTypes),
    counts: {
      widgets: typeof counts.widgets === "number" ? counts.widgets : 0,
      pages: typeof counts.pages === "number" ? counts.pages : 0,
      tools: typeof counts.tools === "number" ? counts.tools : 0,
      recordTypes: typeof counts.recordTypes === "number" ? counts.recordTypes : 0,
    },
  };
}

/**
 * 调用模块自身的 RPC。调用方只能拿到自己的结果；错误沿用 ApiError，
 * 让每张卡片独立降级，而不是整块消失。
 */
export async function callModuleRpc<T = unknown>(
  moduleId: string,
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const body = await requestJson<{ result?: T }>(
    `/modules/${encodeURIComponent(moduleId)}/rpc`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, params }),
    },
    RPC_TIMEOUT_MS,
  );
  return body.result as T;
}

export const MODULE_QUERY_KEY = ["modules"] as const;
export const MODULE_AUDIT_KEY = ["modules", "audit"] as const;
export const MODULE_CONTRIBUTIONS_KEY = ["modules", "contributions"] as const;

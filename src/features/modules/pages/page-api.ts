import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";

/**
 * 模块声明式页面的数据层。
 *
 * 契约事实源是 `schemas/module.schema.json`（$defs/page*）；这里同时兼容任务
 * 提示词里的 `dataSource` / `rowsPath` / `submit.method` 别名，渲染器只认
 * 归一化后的形状。第三方仍然只能交 JSON，不会执行任何代码。
 */

const DEFAULT_TIMEOUT_MS = 30_000;

export const PAGE_CONTRIBUTIONS_KEY = ["modules", "page-contributions"] as const;

/** 同一页面内多个块共用同一数据源时复用缓存。 */
export function pageRpcQueryKey(
  moduleId: string,
  source: ModuleRpcSource | undefined,
) {
  return [
    "modules",
    "page-rpc",
    moduleId,
    source?.method ?? "",
    source?.params ?? {},
  ] as const;
}

export type PageValueFormat = "text" | "number" | "date" | "datetime";

export type PageFieldType =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "select"
  | "checkbox";

export interface ModuleRpcSource {
  type: "module-rpc";
  method: string;
  params?: Record<string, unknown>;
}

export interface PageColumn {
  key: string;
  label: string;
  unit?: string;
  format?: PageValueFormat;
}

export interface PageFieldOption {
  value: string;
  label: string;
}

export interface PageFormField {
  key: string;
  label: string;
  type: PageFieldType;
  required: boolean;
  default?: string | number | boolean;
  options: PageFieldOption[];
  /** detail 块复用 column 形状时携带的显示信息；form 忽略。 */
  unit?: string;
  format?: PageValueFormat;
}

export interface PageBlock {
  component: string;
  title?: string;
  text?: string;
  source?: ModuleRpcSource;
  itemPath?: string;
  primaryPath?: string;
  secondaryPath?: string;
  rowPath?: string;
  columns: PageColumn[];
  fields: PageFormField[];
  submitMethod?: string;
}

export interface ModulePageDefinition {
  id: string;
  title: string;
  icon?: string;
  layout: PageBlock[];
}

export interface PageContribution extends ModulePageDefinition {
  moduleId: string;
  moduleName: string;
  moduleVersion: string;
  moduleType: string;
}

const FIELD_TYPES: readonly PageFieldType[] = [
  "text",
  "textarea",
  "number",
  "date",
  "select",
  "checkbox",
];

const VALUE_FORMATS: readonly PageValueFormat[] = [
  "text",
  "number",
  "date",
  "datetime",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

function normalizeSource(value: unknown): ModuleRpcSource | undefined {
  if (!isRecord(value) || value.type !== "module-rpc") return undefined;
  const method = stringField(value.method, 128);
  if (!method) return undefined;
  const source: ModuleRpcSource = { type: "module-rpc", method };
  if (isRecord(value.params)) source.params = value.params;
  return source;
}

function normalizeFormat(value: unknown): PageValueFormat | undefined {
  return typeof value === "string" &&
    (VALUE_FORMATS as readonly string[]).includes(value)
    ? (value as PageValueFormat)
    : undefined;
}

function normalizeColumn(value: unknown): PageColumn | null {
  if (!isRecord(value)) return null;
  const key = stringField(value.key, 128);
  const label = stringField(value.label, 120);
  if (!key || !label) return null;
  const column: PageColumn = { key, label };
  const unit = stringField(value.unit, 32);
  if (unit) column.unit = unit;
  const format = normalizeFormat(value.format);
  if (format) column.format = format;
  return column;
}

function normalizeOptions(value: unknown): PageFieldOption[] {
  if (!Array.isArray(value)) return [];
  const options: PageFieldOption[] = [];
  for (const raw of value) {
    if (!isRecord(raw)) continue;
    const optionValue = stringField(raw.value, 120);
    const label = stringField(raw.label, 120);
    if (optionValue === undefined || !label) continue;
    options.push({ value: optionValue, label });
  }
  return options.slice(0, 64);
}

function normalizeField(value: unknown): PageFormField | null {
  if (!isRecord(value)) return null;
  const key = stringField(value.key, 128);
  const label = stringField(value.label, 120);
  if (!key || !label) return null;
  const type =
    typeof value.type === "string" &&
    (FIELD_TYPES as readonly string[]).includes(value.type)
      ? (value.type as PageFieldType)
      : "text";
  const field: PageFormField = {
    key,
    label,
    type,
    required: value.required === true,
    options: normalizeOptions(value.options),
  };
  const unit = stringField(value.unit, 32);
  if (unit) field.unit = unit;
  const format = normalizeFormat(value.format);
  if (format) field.format = format;
  const fallback = value.default;
  if (
    typeof fallback === "string" ||
    typeof fallback === "number" ||
    typeof fallback === "boolean"
  ) {
    field.default = fallback;
  }
  return field;
}

function normalizeBlock(value: unknown): PageBlock | null {
  if (!isRecord(value)) return null;
  const component = stringField(value.component, 64);
  if (!component) return null;

  const block: PageBlock = { component, columns: [], fields: [] };
  const title = stringField(value.title, 120);
  if (title) block.title = title;
  if (typeof value.text === "string") block.text = value.text.slice(0, 2000);

  const source = normalizeSource(value.source ?? value.dataSource);
  if (source) block.source = source;

  const itemPath = stringField(value.itemPath ?? value.itemsPath, 128);
  if (itemPath) block.itemPath = itemPath;
  const primaryPath = stringField(value.primaryPath, 128);
  if (primaryPath) block.primaryPath = primaryPath;
  const secondaryPath = stringField(value.secondaryPath, 128);
  if (secondaryPath) block.secondaryPath = secondaryPath;
  const rowPath = stringField(value.rowPath ?? value.rowsPath, 128);
  if (rowPath) block.rowPath = rowPath;

  if (Array.isArray(value.columns)) {
    block.columns = value.columns
      .map(normalizeColumn)
      .filter((column): column is PageColumn => column !== null)
      .slice(0, 32);
  }
  if (Array.isArray(value.fields)) {
    block.fields = value.fields
      .map(normalizeField)
      .filter((field): field is PageFormField => field !== null)
      .slice(0, 64);
  }

  const submit = isRecord(value.submit) ? value.submit : undefined;
  const submitMethod = stringField(
    value.submitMethod ?? submit?.method,
    128,
  );
  if (submitMethod) block.submitMethod = submitMethod;

  return block;
}

function normalizePage(value: unknown): PageContribution | null {
  if (!isRecord(value)) return null;
  const id = stringField(value.id, 64);
  const title = stringField(value.title, 120);
  const moduleId = stringField(value.moduleId, 256);
  if (!id || !title || !moduleId || !Array.isArray(value.layout)) return null;

  const layout = value.layout
    .map(normalizeBlock)
    .filter((block): block is PageBlock => block !== null)
    .slice(0, 64);
  if (layout.length === 0) return null;

  const page: PageContribution = {
    id,
    title,
    layout,
    moduleId,
    moduleName: stringField(value.moduleName, 120) ?? moduleId,
    moduleVersion: stringField(value.moduleVersion, 64) ?? "",
    moduleType: stringField(value.moduleType, 64) ?? "",
  };
  const icon = stringField(value.icon, 64);
  if (icon) page.icon = icon;
  return page;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
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
      // 非 JSON 错误体保留通用文案。
    }
    throw new ApiError(message, { status: response.status, code, details });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function listPageContributions(): Promise<PageContribution[]> {
  const body = await requestJson<unknown>("/modules/contributions?type=pages");
  const items = isRecord(body) && Array.isArray(body.items) ? body.items : [];
  return items
    .map(normalizePage)
    .filter((page): page is PageContribution => page !== null);
}

/**
 * 调用声明页面的模块自身 RPC。核心返回 `{ moduleId, method, result }`，
 * 这里只把 `result` 交给渲染器。
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
  );
  return body.result as T;
}

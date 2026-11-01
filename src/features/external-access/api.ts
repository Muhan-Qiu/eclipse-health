import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";
import {
  isExternalScope,
  type CreatedExternalKey,
  type CreateExternalKeyInput,
  type ExternalKey,
  type ExternalKeysState,
  type ExternalScope,
} from "./types";

const DEFAULT_TIMEOUT_MS = 15_000;

/** 外部接口与普通业务接口同源，只是多一层 `/external` 前缀。 */
export const EXTERNAL_API_BASE = `${baseUrl}/external`;
export const EXTERNAL_RECORDS_URL = `${EXTERNAL_API_BASE}/records`;
export const OPENAI_API_BASE = `${EXTERNAL_API_BASE}/openai/v1`;
export const OPENAI_MODEL = "eclipse-health";
export const MCP_COMMAND = "python -m eclipse_health_backend.mcp_server";

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function asScopes(value: unknown): ExternalScope[] {
  return Array.isArray(value) ? value.filter(isExternalScope) : [];
}

function normalizeKey(value: unknown): ExternalKey | null {
  const item = asRecord(value);
  const id = asString(item.id);
  const name = asString(item.name);
  if (!id || !name) return null;
  return {
    id,
    name,
    prefix: asString(item.prefix),
    scopes: asScopes(item.scopes),
    createdAt: asString(item.createdAt),
    lastUsedAt: asNullableString(item.lastUsedAt),
    revokedAt: asNullableString(item.revokedAt),
  };
}

function normalizeKeys(value: unknown): ExternalKey[] {
  const items = asRecord(value).items;
  if (!Array.isArray(items)) return [];
  return items
    .map(normalizeKey)
    .filter((item): item is ExternalKey => item !== null);
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
    response = await fetch(`${EXTERNAL_API_BASE}${path}`, {
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

/** 404 与网络层失败都意味着后端没有提供外部访问，可作为降级的同义词。 */
export function isExternalUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 || error.status === undefined)
  );
}

export async function listExternalKeys(): Promise<ExternalKeysState> {
  try {
    const body = await requestJson<unknown>("/keys");
    return { status: "ok", items: normalizeKeys(body) };
  } catch (error) {
    if (isExternalUnavailable(error)) return { status: "unavailable" };
    throw error;
  }
}

export async function createExternalKey(
  input: CreateExternalKeyInput,
): Promise<CreatedExternalKey> {
  const body = asRecord(
    await requestJson<unknown>("/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: input.name, scopes: input.scopes }),
    }),
  );
  const id = asString(body.id);
  const token = asString(body.token);
  if (!id || !token) {
    throw new ApiError("创建 API Key 失败：响应缺少 token", {
      code: "invalid_response",
    });
  }
  return {
    id,
    name: asString(body.name, input.name),
    token,
    prefix: asString(body.prefix),
    scopes: asScopes(body.scopes),
    createdAt: asString(body.createdAt),
  };
}

export async function revokeExternalKey(id: string): Promise<void> {
  await requestJson<unknown>(`/keys/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

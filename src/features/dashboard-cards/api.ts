/**
 * 自定义卡片 API 客户端。
 *
 * 复用共享的 `baseUrl` / `ApiError`；不引入新的请求依赖。
 */
import { ApiError, baseUrl } from "@/lib/api/client";
import type {
  CardCreateInput,
  CardDraft,
  CardTemplate,
  CustomCardKind,
  DashboardCard,
  CardAggregation,
  CardView,
  ColorToken,
} from "./types";

const TIMEOUT_MS = 15_000;

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
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
    // 非 JSON 错误体保留通用文案
  }
  return new ApiError(message, { status: response.status, code, details });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      signal: controller.signal,
      headers: { Accept: "application/json", ...init.headers },
    });
    if (!response.ok) throw await responseError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时，请检查后端是否正在运行", { code: "timeout" });
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError("无法连接到本地后端", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }
}

function jsonRequest<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<T> {
  return request<T>(path, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export interface CardPatch {
  title?: string;
  kind?: CustomCardKind;
  aggregation?: CardAggregation;
  windowDays?: number;
  view?: CardView;
  unit?: string | null;
  colorToken?: ColorToken;
}

export const dashboardCardsApi = {
  list: async (memberId?: string): Promise<DashboardCard[]> => {
    const body = await request<{ items?: DashboardCard[] }>(
      `/dashboard/cards${query({ memberId, includeData: "true" })}`,
    );
    return Array.isArray(body.items) ? body.items : [];
  },

  data: (cardId: string, memberId?: string) =>
    request<DashboardCard["data"]>(
      `/dashboard/cards/${encodeURIComponent(cardId)}/data${query({ memberId })}`,
    ),

  create: (input: CardCreateInput) =>
    jsonRequest<DashboardCard>("/dashboard/cards", "POST", input),

  update: (cardId: string, patch: CardPatch, memberId?: string) =>
    jsonRequest<DashboardCard>(
      `/dashboard/cards/${encodeURIComponent(cardId)}${query({ memberId })}`,
      "PATCH",
      patch,
    ),

  remove: (cardId: string, memberId?: string) =>
    jsonRequest<void>(
      `/dashboard/cards/${encodeURIComponent(cardId)}${query({ memberId })}`,
      "DELETE",
    ),

  templates: async (): Promise<CardTemplate[]> => {
    const body = await request<CardTemplate[]>("/dashboard/card-templates");
    return Array.isArray(body) ? body : [];
  },

  drafts: async (memberId?: string): Promise<CardDraft[]> => {
    const body = await request<{ items?: CardDraft[] }>(
      `/dashboard/card-drafts${query({ memberId })}`,
    );
    return Array.isArray(body.items) ? body.items : [];
  },

  confirmDraft: (draftId: string, memberId?: string) =>
    jsonRequest<DashboardCard>(
      `/dashboard/card-drafts/${encodeURIComponent(draftId)}/confirm${query({
        memberId,
      })}`,
      "POST",
    ),

  discardDraft: (draftId: string, memberId?: string) =>
    jsonRequest<void>(
      `/dashboard/card-drafts/${encodeURIComponent(draftId)}${query({ memberId })}`,
      "DELETE",
    ),
};

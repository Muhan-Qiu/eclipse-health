/**
 * 助手功能的本地 API 客户端。
 *
 * 只复用共享 `baseUrl` / `ApiError` / 类型，不改 `src/lib/api/*`。
 * SSE 用 fetch + ReadableStream 手工解析，避免引入新依赖。
 */
import { ApiError, baseUrl } from "@/lib/api/client";
import type { RecordPage } from "@/lib/api/types";
import type {
  AssistantProvider,
  AssistantSession,
  CoachWeather,
  MessagePage,
  ProviderInput,
  ProviderPreset,
  ProviderTestResult,
  SendMessageBody,
  StreamEvent,
  Transparency,
} from "./types";

const DEFAULT_TIMEOUT_MS = 15_000;

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
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
    throw new ApiError("无法连接到本地后端", { code: "network_error", cause: error });
  } finally {
    clearTimeout(timer);
  }
}

async function requestJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function parseSseChunk(raw: string): StreamEvent | null {
  let name = "";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!name) return null;
  try {
    return { event: name, data: JSON.parse(data.join("\n")) } as StreamEvent;
  } catch {
    return null;
  }
}

export const assistantApi = {
  providers: {
    presets: async (): Promise<ProviderPreset[]> => {
      const body = await request<{ items: ProviderPreset[] }>(
        "/assistant/provider-presets",
      );
      return Array.isArray(body.items) ? body.items : [];
    },
    list: async (): Promise<AssistantProvider[]> => {
      const body = await request<{ items: AssistantProvider[] }>("/assistant/providers");
      return Array.isArray(body.items) ? body.items : [];
    },
    save: (id: string, input: ProviderInput): Promise<AssistantProvider> =>
      requestJson<AssistantProvider>(
        `/assistant/providers/${encodeURIComponent(id)}`,
        "PUT",
        input,
      ),
    remove: (id: string): Promise<void> =>
      requestJson<void>(`/assistant/providers/${encodeURIComponent(id)}`, "DELETE"),
    test: (id: string): Promise<ProviderTestResult> =>
      requestJson<ProviderTestResult>(
        `/assistant/providers/${encodeURIComponent(id)}/test`,
        "POST",
      ),
  },

  sessions: {
    list: async (params: {
      q?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<AssistantSession[]> => {
      const query = new URLSearchParams();
      if (params.q && params.q.trim()) query.set("q", params.q.trim());
      if (params.limit) query.set("limit", String(params.limit));
      if (params.offset) query.set("offset", String(params.offset));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const body = await request<{ items: AssistantSession[] }>(
        `/assistant/sessions${suffix}`,
      );
      return Array.isArray(body.items) ? body.items : [];
    },
    create: (input: {
      title?: string;
      providerId?: string | null;
      style?: string;
      recordId?: string | null;
    }): Promise<AssistantSession> =>
      requestJson<AssistantSession>("/assistant/sessions", "POST", input),
    rename: (id: string, title: string): Promise<AssistantSession> =>
      requestJson<AssistantSession>(
        `/assistant/sessions/${encodeURIComponent(id)}`,
        "PATCH",
        { title },
      ),
    remove: (id: string): Promise<void> =>
      requestJson<void>(`/assistant/sessions/${encodeURIComponent(id)}`, "DELETE"),
    messages: async (
      id: string,
      options: { limit?: number; offset?: number; order?: "asc" | "desc" } = {},
    ): Promise<MessagePage> => {
      const query = new URLSearchParams();
      if (options.limit) query.set("limit", String(options.limit));
      if (options.offset !== undefined) query.set("offset", String(options.offset));
      if (options.order) query.set("order", options.order);
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const body = await request<MessagePage>(
        `/assistant/sessions/${encodeURIComponent(id)}/messages${suffix}`,
      );
      return {
        items: Array.isArray(body.items) ? body.items : [],
        total: typeof body.total === "number" ? body.total : 0,
        limit: typeof body.limit === "number" ? body.limit : 200,
        offset: typeof body.offset === "number" ? body.offset : 0,
        hasMore: Boolean(body.hasMore),
      };
    },
    /** 导出 Markdown 文本；调用方负责触发下载（避免 api 层碰 DOM）。 */
    exportMarkdown: async (
      id: string,
      options: { includeToolArgs?: boolean } = {},
    ): Promise<{ text: string; filename: string }> => {
      const query = new URLSearchParams();
      if (options.includeToolArgs) query.set("includeToolArgs", "true");
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await fetch(
        `${baseUrl}/assistant/sessions/${encodeURIComponent(id)}/export${suffix}`,
        { credentials: "omit", headers: { Accept: "text/markdown" } },
      );
      if (!response.ok) throw await responseError(response);
      const disposition = response.headers.get("content-disposition") ?? "";
      const match = /filename="([^"]+)"/.exec(disposition);
      return {
        text: await response.text(),
        filename: match?.[1] ?? "eclipse-health-assistant.md",
      };
    },
  },

  messages: {
    transparency: (id: string): Promise<Transparency> =>
      request<Transparency>(
        `/assistant/messages/${encodeURIComponent(id)}/transparency`,
      ),
    cancel: (id: string): Promise<{ messageId: string; cancelled: boolean; status: string }> =>
      requestJson<{ messageId: string; cancelled: boolean; status: string }>(
        `/assistant/messages/${encodeURIComponent(id)}/cancel`,
        "POST",
      ),
  },

  records: {
    list: async (): Promise<RecordPage> =>
      request<RecordPage>("/records?limit=30&recordType=org.eclipsehealth.ecg"),
  },

  coach: {
    /** 天气失败/接口未挂载时返回 null；调用方不要把它当成错误。 */
    weather: async (city: string): Promise<CoachWeather | null> => {
      const trimmed = city.trim();
      if (!trimmed) return null;
      const body = await request<{ weather: CoachWeather | null }>(
        `/coach/weather?city=${encodeURIComponent(trimmed)}`,
      );
      return body.weather ?? null;
    },
  },

  /** POST + SSE；`onEvent` 逐条回调，解析失败的帧会被忽略。 */
  async stream(
    sessionId: string,
    body: SendMessageBody,
    signal: AbortSignal,
    onEvent: (event: StreamEvent) => void,
  ): Promise<void> {
    const response = await fetch(
      `${baseUrl}/assistant/sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: "POST",
        credentials: "omit",
        signal,
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      },
    );
    if (!response.ok) throw await responseError(response);
    if (!response.body) {
      throw new ApiError("流式响应不可用", { code: "stream_unavailable" });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r/g, "");
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          const raw = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const event = parseSseChunk(raw);
          if (event) onEvent(event);
          boundary = buffer.indexOf("\n\n");
        }
      }
    } finally {
      reader.releaseLock();
    }
  },
};

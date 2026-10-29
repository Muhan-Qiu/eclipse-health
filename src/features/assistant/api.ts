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
  ChatMessage,
  ProviderInput,
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
    list: async (): Promise<AssistantSession[]> => {
      const body = await request<{ items: AssistantSession[] }>("/assistant/sessions");
      return Array.isArray(body.items) ? body.items : [];
    },
    create: (input: {
      title?: string;
      providerId?: string | null;
      style?: string;
      recordId?: string | null;
    }): Promise<AssistantSession> =>
      requestJson<AssistantSession>("/assistant/sessions", "POST", input),
    remove: (id: string): Promise<void> =>
      requestJson<void>(`/assistant/sessions/${encodeURIComponent(id)}`, "DELETE"),
    messages: async (id: string): Promise<ChatMessage[]> => {
      const body = await request<{ items: ChatMessage[] }>(
        `/assistant/sessions/${encodeURIComponent(id)}/messages`,
      );
      return Array.isArray(body.items) ? body.items : [];
    },
  },

  messages: {
    transparency: (id: string): Promise<Transparency> =>
      request<Transparency>(
        `/assistant/messages/${encodeURIComponent(id)}/transparency`,
      ),
  },

  records: {
    list: async (): Promise<RecordPage> =>
      request<RecordPage>("/records?limit=30&recordType=org.eclipsehealth.ecg"),
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

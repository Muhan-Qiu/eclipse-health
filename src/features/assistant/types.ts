/** 助手功能的本地类型（与 api/assistant.py 的 camelCase 响应对齐）。 */

export type ProviderKind = "openai" | "anthropic" | "ollama" | "mock";
export type AssistantStyle = "brief" | "detailed" | "doctor";
export type MessageStatus = "streaming" | "completed" | "error" | "cancelled";

export interface AssistantProvider {
  id: string;
  kind: ProviderKind;
  label: string;
  model: string;
  baseUrl: string | null;
  enabled: boolean;
  configured: boolean;
  isLocal: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ProviderInput {
  kind: ProviderKind;
  label: string;
  model: string;
  baseUrl?: string | null;
  enabled?: boolean;
  apiKey?: string;
  clearKey?: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  providerId: string;
  kind: string;
  model: string;
  latencyMs: number | null;
  message: string;
  /** 模型是否已安装/可用；无法判断时为 null。 */
  available: boolean | null;
  /** 是否声明支持 tool calling；无法判断时为 null。 */
  supportsTools: boolean | null;
  models: string[];
}

export interface Usage {
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  source: "provider" | "estimate" | string;
}

export interface AssistantSession {
  id: string;
  title: string;
  providerId: string | null;
  style: AssistantStyle;
  recordId: string | null;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
  hasNotes: boolean;
}

export interface ToolCallTrace {
  id: string;
  messageId?: string;
  name: string;
  args: Record<string, unknown>;
  resultSummary: string;
  ok: boolean;
  durationMs: number;
  createdAt?: string;
  /** 仅前端流式阶段使用：工具已调用、结果尚未返回。 */
  pending?: boolean;
}

export interface Citation {
  kind: "record" | "analysis" | "trend" | "model" | string;
  id: string;
  label?: string;
  recordId?: string;
}

export interface Transparency {
  provider: { id: string; kind: ProviderKind; label: string; model: string };
  model: string;
  sentFields: string[];
  redactions: string[];
  approxTokens: number;
  recordIds: string[];
  analysisIds: string[];
  includeNotes: boolean;
  toolCalls: number;
  usage?: Usage | null;
  localOnly: boolean;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  providerId?: string | null;
  style?: string | null;
  citations: Citation[];
  error?: { code: string; message: string } | null;
  toolCalls: ToolCallTrace[];
  transparency?: Transparency | null;
  usage?: Usage | null;
  durationMs?: number | null;
  model?: string | null;
  /** 服务端消息 ID（流式开始时由 start 事件带回）。 */
  serverId?: string;
  createdAt: string;
}

export interface MessagePage {
  items: ChatMessage[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface SendMessageBody {
  content: string;
  style: AssistantStyle;
  providerId: string;
  recordId?: string;
  includeNotes?: boolean;
}

export type StreamEvent =
  | {
      event: "start";
      data: {
        sessionId: string;
        userMessageId: string;
        assistantMessageId: string;
        provider: { id: string; kind: ProviderKind; label: string; model: string };
      };
    }
  | { event: "token"; data: { text: string } }
  | {
      event: "tool_call";
      data: { id: string; name: string; args: Record<string, unknown> };
    }
  | {
      event: "tool_result";
      data: {
        id: string;
        name: string;
        ok: boolean;
        durationMs: number;
        resultSummary: string;
      };
    }
  | { event: "citation"; data: Citation }
  | {
      event: "done";
      data: {
        content: string;
        citations: Citation[];
        toolCalls: number;
        transparency?: Transparency;
        usage?: Usage | null;
        durationMs?: number;
        cancelled?: boolean;
      };
    }
  | { event: "error"; data: { code: string; message: string } };

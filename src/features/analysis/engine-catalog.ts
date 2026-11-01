import { baseUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";

/**
 * 分析引擎目录（C7）。
 *
 * 只属于记录详情特性：刻意不放进 `src/lib/api/*`，避免与同时在改的
 * API 层冲突。后端 `GET /analyses/engines` 是唯一事实源。
 */
export interface EngineDescriptor {
  id: string;
  name: string;
  moduleId: string;
  modelId: string;
  modelVersion: string;
  available: boolean;
  reason: string | null;
}

const TIMEOUT_MS = 15_000;

function normalizeEngine(raw: unknown): EngineDescriptor | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.id !== "string" || !item.id) return null;
  return {
    id: item.id,
    name: typeof item.name === "string" ? item.name : item.id,
    moduleId: typeof item.moduleId === "string" ? item.moduleId : "",
    modelId: typeof item.modelId === "string" ? item.modelId : "",
    modelVersion: typeof item.modelVersion === "string" ? item.modelVersion : "",
    // 缺字段时按可用处理，兼容尚未升级的后端。
    available: item.available !== false,
    reason: typeof item.reason === "string" ? item.reason : null,
  };
}

export async function fetchEngineCatalog(
  signal?: AbortSignal,
): Promise<EngineDescriptor[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort);

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/analyses/engines`, {
      credentials: "omit",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      // 外部取消（组件卸载/新请求）交由 React Query 处理；超时给出可读错误。
      if (signal?.aborted) throw error;
      throw new ApiError("请求超时", { code: "timeout", cause: error });
    }
    throw new ApiError("无法连接本地后端", { code: "network_error", cause: error });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
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

  const body = (await response.json()) as Record<string, unknown>;
  const items = Array.isArray(body.items) ? body.items : [];
  return items
    .map(normalizeEngine)
    .filter((item): item is EngineDescriptor => item !== null);
}

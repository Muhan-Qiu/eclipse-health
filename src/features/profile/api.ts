import { ApiError, api, baseUrl, useMock } from "@/lib/api/client";
import type { Member } from "@/lib/api/types";
import type {
  MemberPatch,
  Metric,
  MetricInput,
  MetricKind,
  MetricListParams,
  MetricPage,
  MetricPatch,
} from "./types";
import { METRIC_UNITS } from "./types";

const TIMEOUT_MS = 15_000;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
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
        // 非 JSON 错误体保留通用文案
      }
      throw new ApiError(message, {
        status: response.status,
        code,
        details,
      });
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时，请检查后端是否正在运行", {
        code: "timeout",
        cause: error,
      });
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

/* ------------------------------------------------------------------ *
 * Mock 模式：只保存在内存里，方便无后端演示；离开页面即丢弃。
 * ------------------------------------------------------------------ */

let mockSeq = 0;
const mockMetrics: Metric[] = [];

function nowIso(): string {
  return new Date().toISOString();
}

function mockMetric(input: MetricInput): Metric {
  mockSeq += 1;
  const timestamp = nowIso();
  return {
    id: `rec_mock_metric_${mockSeq}`,
    memberId: input.memberId ?? "mem_mock",
    kind: input.kind,
    measuredAt: input.measuredAt,
    timezone: input.timezone ?? "UTC",
    values: input.values,
    unit: METRIC_UNITS[input.kind],
    notes: input.notes ?? "",
    tags: input.tags ?? [],
    warnings: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export async function listMetrics(params: MetricListParams = {}): Promise<MetricPage> {
  if (useMock) {
    const filtered = params.kind
      ? mockMetrics.filter((item) => item.kind === params.kind)
      : mockMetrics;
    return {
      items: filtered,
      total: filtered.length,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    };
  }
  return request<MetricPage>(
    `/metrics${query({
      kind: params.kind,
      from: params.from,
      to: params.to,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export async function createMetric(input: MetricInput): Promise<Metric> {
  if (useMock) {
    const metric = mockMetric(input);
    mockMetrics.unshift(metric);
    return metric;
  }
  return request<Metric>("/metrics", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateMetric(id: string, patch: MetricPatch): Promise<Metric> {
  if (useMock) {
    const current = mockMetrics.find((item) => item.id === id);
    if (!current) {
      throw new ApiError("指标不存在", { status: 404, code: "metric_not_found" });
    }
    const updated: Metric = {
      ...current,
      ...patch,
      values: patch.values ?? current.values,
      updatedAt: nowIso(),
    };
    const index = mockMetrics.indexOf(current);
    mockMetrics[index] = updated;
    return updated;
  }
  return request<Metric>(`/metrics/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteMetric(id: string): Promise<void> {
  if (useMock) {
    const index = mockMetrics.findIndex((item) => item.id === id);
    if (index >= 0) mockMetrics.splice(index, 1);
    return;
  }
  await request<void>(`/metrics/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function updateMember(
  id: string,
  patch: MemberPatch,
  currentMember?: Member,
): Promise<Member> {
  if (useMock) {
    const members = await api.members.list();
    const current =
      currentMember ?? members.find((member) => member.id === id) ?? members[0];
    if (!current) {
      throw new ApiError("成员不存在", { status: 404, code: "member_not_found" });
    }
    return { ...current, ...patch, updatedAt: nowIso() } as Member;
  }
  return request<Member>(`/members/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** 通知 watcher 用：只读取最近记录的最新分析状态。 */
export async function listRecentRecords(limit = 20) {
  return api.records.list({ limit });
}

export type { Metric, MetricKind };

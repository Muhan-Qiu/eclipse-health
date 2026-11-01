/**
 * Agent 数据导入前端客户端（docs/IMPORT_AGENT_API.md）。
 *
 * 标准 preview 无法识别时，用户可把文件交给后端 Agent：
 * 创建 session → SSE 运行 → 分组预览 → commit。
 * 事件名、字段名与后端契约保持一致；演示模式在本地模拟同一套事件。
 */

import { ApiError } from "@/lib/api/error";
import { apiMode, baseUrl } from "@/lib/api/client";

export type AgentSessionStatus =
  | "created"
  | "running"
  | "ready"
  | "error"
  | "committed";

export interface AgentFile {
  name: string;
  storedName?: string;
  size: number;
  sha256?: string;
  kind?: string;
}

export interface AgentSource {
  kind?: string;
  app?: string | null;
  device?: string | null;
  manufacturer?: string | null;
}

export interface AgentEvidence {
  file: string;
  locator?: string;
  snippet?: string;
  page?: number;
  line?: number;
}

export interface AgentProposal {
  id: string;
  kind: string;
  recordType: string;
  value: unknown;
  unit: string;
  startAt: string;
  endAt: string | null;
  durationSec?: number | null;
  source: AgentSource;
  evidence: AgentEvidence;
  confidence: number;
  tags?: string[];
  notes?: string;
  metric?: string;
  payload?: Record<string, unknown>;
  fingerprint?: string;
  createdAt?: string;
}

export interface AgentSession {
  sessionId: string;
  status: AgentSessionStatus;
  createdAt: string;
  expiresAt: string;
  files: AgentFile[];
  proposalCount: number;
  summary: string | null;
  toolCalls?: number;
  lastError: { code: string; message: string } | null;
  commit: AgentCommitResult | null;
  proposals?: AgentProposal[];
  proposalsTruncated?: boolean;
}

export interface AgentLimits {
  maxFiles?: number;
  maxUploadBytes?: number;
  maxToolCalls?: number;
  maxTurnSeconds?: number;
  maxRunSeconds?: number;
  maxProposalRecords?: number;
  network?: boolean;
}

export interface AgentStatusEvent {
  phase: string;
  provider?: string;
  files?: number;
  limits?: AgentLimits;
  toolCalls?: number;
  elapsedMs?: number;
  network?: boolean;
}

export interface AgentToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  index?: number;
}

export interface AgentToolResult {
  id: string;
  name: string;
  ok: boolean;
  durationMs?: number;
  resultSummary?: string;
  error?: string;
}

export interface AgentPreviewEvent {
  count: number;
  total: number;
  items: AgentProposal[];
  issues?: unknown[];
}

export interface AgentDoneEvent {
  summary?: string;
  proposalCount: number;
  toolCalls?: number;
  durationMs?: number;
  status?: string;
}

export interface AgentErrorEvent {
  code: string;
  message: string;
  details?: unknown;
}

export interface AgentRunHandlers {
  onStatus?: (event: AgentStatusEvent) => void;
  onToken?: (text: string) => void;
  onToolCall?: (event: AgentToolCall) => void;
  onToolResult?: (event: AgentToolResult) => void;
  onPreview?: (event: AgentPreviewEvent) => void;
  onDone?: (event: AgentDoneEvent) => void;
  onError?: (event: AgentErrorEvent) => void;
}

export interface AgentRunOptions extends AgentRunHandlers {
  providerId?: string;
  instructions?: string;
  signal?: AbortSignal;
}

export interface AgentCommitResult {
  sessionId: string;
  created: number;
  skipped: number;
  failed: number;
  duplicateCommit?: boolean;
  recordIds?: string[];
  counts?: Record<string, number>;
  errors?: Array<{ id?: string; code?: string; message?: string }>;
}

const AGENT_TIMEOUT_MS = 30_000;
const AGENT_RUN_TIMEOUT_MS = 200_000;

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeFile(value: unknown): AgentFile {
  const item = asRecord(value);
  return {
    name: str(item.name, str(item.storedName)),
    storedName: str(item.storedName) || undefined,
    size: num(item.size),
    sha256: str(item.sha256) || undefined,
    kind: str(item.kind) || undefined,
  };
}

function normalizeProposal(value: unknown): AgentProposal {
  const item = asRecord(value);
  const source = asRecord(item.source);
  const evidence = asRecord(item.evidence);
  return {
    id: str(item.id),
    kind: str(item.kind),
    recordType: str(item.recordType),
    value: item.value,
    unit: str(item.unit),
    startAt: str(item.startAt),
    endAt: typeof item.endAt === "string" ? item.endAt : null,
    durationSec:
      typeof item.durationSec === "number" ? item.durationSec : null,
    source: {
      kind: str(source.kind) || undefined,
      app: typeof source.app === "string" ? source.app : null,
      device: typeof source.device === "string" ? source.device : null,
      manufacturer:
        typeof source.manufacturer === "string" ? source.manufacturer : null,
    },
    evidence: {
      file: str(evidence.file),
      locator: str(evidence.locator) || undefined,
      snippet: str(evidence.snippet) || undefined,
      page: typeof evidence.page === "number" ? evidence.page : undefined,
      line: typeof evidence.line === "number" ? evidence.line : undefined,
    },
    confidence: num(item.confidence, 0),
    tags: Array.isArray(item.tags)
      ? item.tags.filter((tag): tag is string => typeof tag === "string")
      : [],
    notes: str(item.notes) || undefined,
    metric: str(item.metric) || undefined,
    payload: asRecord(item.payload),
    fingerprint: str(item.fingerprint) || undefined,
    createdAt: str(item.createdAt) || undefined,
  };
}

function normalizeSession(value: unknown): AgentSession {
  const item = asRecord(value);
  const files = Array.isArray(item.files) ? item.files.map(normalizeFile) : [];
  const proposals = Array.isArray(item.proposals)
    ? item.proposals.map(normalizeProposal)
    : undefined;
  const lastError = asRecord(item.lastError);
  const commit = asRecord(item.commit);
  return {
    sessionId: str(item.sessionId),
    status: (str(item.status, "created") as AgentSessionStatus) ?? "created",
    createdAt: str(item.createdAt),
    expiresAt: str(item.expiresAt),
    files,
    proposalCount: num(item.proposalCount),
    summary: typeof item.summary === "string" ? item.summary : null,
    toolCalls: num(item.toolCalls),
    lastError:
      typeof item.lastError === "object" && item.lastError !== null
        ? { code: str(lastError.code), message: str(lastError.message) }
        : null,
    commit:
      commit.sessionId || commit.created !== undefined
        ? (commit as unknown as AgentCommitResult)
        : null,
    proposals,
    proposalsTruncated: item.proposalsTruncated === true,
  };
}

async function requestJson(
  path: string,
  init: RequestInit = {},
  timeoutMs = AGENT_TIMEOUT_MS,
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "omit",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Agent 请求超时，请检查后端是否正在运行", {
        code: "timeout",
        cause: error,
      });
    }
    throw new ApiError("无法连接到本地后端", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = `请求失败（${response.status}）`;
    try {
      const body = asRecord(await response.json());
      if (typeof body.code === "string") code = body.code;
      if (typeof body.message === "string") message = body.message;
    } catch {
      // 非 JSON 错误体保留通用文案
    }
    throw new ApiError(message, { status: response.status, code });
  }
  if (response.status === 204) return null;
  return response.json();
}

/* ------------------------------------------------------------------ *
 * 真实客户端
 * ------------------------------------------------------------------ */

export async function createAgentSession(files: File[]): Promise<AgentSession> {
  if (apiMode.mock) return mockCreateSession(files);
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  return normalizeSession(
    await requestJson(
      "/import-agent/sessions",
      { method: "POST", body: form },
      AGENT_RUN_TIMEOUT_MS,
    ),
  );
}

export async function getAgentSession(sessionId: string): Promise<AgentSession> {
  if (apiMode.mock) return mockGetSession(sessionId);
  return normalizeSession(
    await requestJson(
      `/import-agent/sessions/${encodeURIComponent(sessionId)}`,
    ),
  );
}

export async function fetchAllAgentProposals(
  sessionId: string,
  max = 5000,
): Promise<AgentProposal[]> {
  if (apiMode.mock) return mockGetProposals(sessionId);
  const collected: AgentProposal[] = [];
  let offset = 0;
  const limit = 500;
  while (collected.length < max) {
    const body = asRecord(
      await requestJson(
        `/import-agent/sessions/${encodeURIComponent(sessionId)}/proposals?limit=${limit}&offset=${offset}`,
      ),
    );
    const items = Array.isArray(body.items)
      ? body.items.map(normalizeProposal)
      : [];
    collected.push(...items);
    offset += items.length;
    if (items.length < limit || offset >= num(body.total)) break;
  }
  return collected;
}

export async function commitAgentSession(
  sessionId: string,
  body: {
    records?: string[];
    memberId?: string;
    timezone?: string;
  } = {},
): Promise<AgentCommitResult> {
  if (apiMode.mock) return mockCommit(sessionId, body);
  const value = asRecord(
    await requestJson(
      `/import-agent/sessions/${encodeURIComponent(sessionId)}/commit`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      AGENT_RUN_TIMEOUT_MS,
    ),
  );
  return {
    sessionId: str(value.sessionId, sessionId),
    created: num(value.created),
    skipped: num(value.skipped),
    failed: num(value.failed),
    duplicateCommit: value.duplicateCommit === true,
    recordIds: Array.isArray(value.recordIds)
      ? value.recordIds.filter((id): id is string => typeof id === "string")
      : [],
    counts: asRecord(value.counts) as Record<string, number>,
    errors: Array.isArray(value.errors)
      ? (value.errors as AgentCommitResult["errors"])
      : [],
  };
}

export async function discardAgentSession(sessionId: string): Promise<void> {
  if (apiMode.mock) {
    mockDiscard(sessionId);
    return;
  }
  try {
    await requestJson(
      `/import-agent/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
      AGENT_TIMEOUT_MS,
    );
  } catch (error) {
    // 已过期或已提交的 session 删除失败不应阻塞用户
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }
}

/** POST + SSE；逐事件回调，直到 done / error / 流结束。 */
export async function runAgentSession(
  sessionId: string,
  options: AgentRunOptions,
): Promise<void> {
  if (apiMode.mock) return mockRun(sessionId, options);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), AGENT_RUN_TIMEOUT_MS);
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });

  try {
    const response = await fetch(
      `${baseUrl}/import-agent/sessions/${encodeURIComponent(sessionId)}/run`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          providerId: options.providerId || undefined,
          instructions: options.instructions?.slice(0, 2000) || undefined,
        }),
        credentials: "omit",
        signal: controller.signal,
      },
    );
    if (!response.ok) {
      let code = `http_${response.status}`;
      let message = `请求失败（${response.status}）`;
      try {
        const body = asRecord(await response.json());
        if (typeof body.code === "string") code = body.code;
        if (typeof body.message === "string") message = body.message;
      } catch {
        // ignore
      }
      throw new ApiError(message, { status: response.status, code });
    }
    if (!response.body) {
      throw new ApiError("SSE 流不可用", { code: "stream_unavailable" });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n\n");
      while (index >= 0) {
        const block = buffer.slice(0, index).replace(/\r/g, "");
        buffer = buffer.slice(index + 2);
        dispatchSseBlock(block, options);
        index = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) dispatchSseBlock(buffer.replace(/\r/g, ""), options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (options.signal?.aborted) {
        options.onError?.({ code: "cancelled", message: "已停止解析" });
        return;
      }
      options.onError?.({
        code: "timeout",
        message: "Agent 运行超时，请稍后重试",
      });
      return;
    }
    if (error instanceof ApiError) {
      options.onError?.({ code: error.code, message: error.message, details: error.details });
      return;
    }
    options.onError?.({
      code: "network_error",
      message: "无法连接到本地后端",
    });
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

function dispatchSseBlock(block: string, handlers: AgentRunHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  const item = asRecord(data);
  switch (event) {
    case "status":
      handlers.onStatus?.({
        phase: str(item.phase, "running"),
        provider: str(item.provider) || undefined,
        files: typeof item.files === "number" ? item.files : undefined,
        limits: asRecord(item.limits) as AgentLimits,
        toolCalls: num(item.toolCalls),
        elapsedMs: num(item.elapsedMs),
        network: item.network === true,
      });
      break;
    case "token":
      handlers.onToken?.(str(item.text));
      break;
    case "tool_call":
      handlers.onToolCall?.({
        id: str(item.id),
        name: str(item.name),
        args: asRecord(item.args),
        index: num(item.index),
      });
      break;
    case "tool_result":
      handlers.onToolResult?.({
        id: str(item.id),
        name: str(item.name),
        ok: item.ok !== false,
        durationMs: num(item.durationMs),
        resultSummary: str(item.resultSummary) || undefined,
        error: str(item.error) || undefined,
      });
      break;
    case "preview":
      handlers.onPreview?.({
        count: num(item.count),
        total: num(item.total),
        items: Array.isArray(item.items)
          ? item.items.map(normalizeProposal)
          : [],
        issues: Array.isArray(item.issues) ? item.issues : undefined,
      });
      break;
    case "done":
      handlers.onDone?.({
        summary: str(item.summary) || undefined,
        proposalCount: num(item.proposalCount),
        toolCalls: num(item.toolCalls),
        durationMs: num(item.durationMs),
        status: str(item.status) || undefined,
      });
      break;
    case "error":
      handlers.onError?.({
        code: str(item.code, "agent_error"),
        message: str(item.message, "Agent 执行失败"),
        details: item.details,
      });
      break;
    default:
      break;
  }
}

/* ------------------------------------------------------------------ *
 * 演示模式：本地模拟同一套事件，便于没有后端时走完整流程
 * ------------------------------------------------------------------ */

interface MockSession {
  session: AgentSession;
  files: File[];
  proposals: AgentProposal[];
}

const mockSessions = new Map<string, MockSession>();
let mockCounter = 0;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function mockCreateSession(files: File[]): AgentSession {
  mockCounter += 1;
  const now = new Date();
  const sessionId = `ias_mock_${mockCounter}_${now.getTime()}`;
  const session: AgentSession = {
    sessionId,
    status: "created",
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + 24 * 3600_000).toISOString(),
    files: files.map((file) => ({
      name: file.name,
      size: file.size,
      kind: file.name.split(".").pop()?.toLowerCase(),
    })),
    proposalCount: 0,
    summary: null,
    toolCalls: 0,
    lastError: null,
    commit: null,
  };
  mockSessions.set(sessionId, { session, files, proposals: [] });
  return session;
}

function mockGetSession(sessionId: string): AgentSession {
  const entry = mockSessions.get(sessionId);
  if (!entry) {
    throw new ApiError("导入会话不存在或已过期", {
      status: 404,
      code: "session_not_found",
    });
  }
  return {
    ...entry.session,
    proposals: entry.proposals.slice(0, 200),
    proposalsTruncated: entry.proposals.length > 200,
  };
}

function mockGetProposals(sessionId: string): AgentProposal[] {
  return mockSessions.get(sessionId)?.proposals ?? [];
}

function mockDiscard(sessionId: string): void {
  mockSessions.delete(sessionId);
}

function mockCommit(
  sessionId: string,
  body: { records?: string[]; memberId?: string; timezone?: string },
): AgentCommitResult {
  const entry = mockSessions.get(sessionId);
  if (!entry) {
    throw new ApiError("导入会话不存在或已过期", {
      status: 404,
      code: "session_not_found",
    });
  }
  if (entry.session.status === "committed" && entry.session.commit) {
    return { ...entry.session.commit, duplicateCommit: true };
  }
  const selected = body.records?.length
    ? entry.proposals.filter((item) => body.records?.includes(item.id))
    : entry.proposals;
  const counts: Record<string, number> = {};
  for (const item of selected) counts[item.kind] = (counts[item.kind] ?? 0) + 1;
  const result: AgentCommitResult = {
    sessionId,
    created: selected.length,
    skipped: 0,
    failed: 0,
    duplicateCommit: false,
    recordIds: selected.map((_, index) => `rec_mock_${index + 1}`),
    counts,
    errors: [],
  };
  entry.session = {
    ...entry.session,
    status: "committed",
    commit: result,
  };
  return result;
}

function iso(offsetMinutes: number): string {
  return new Date(Date.now() - offsetMinutes * 60_000).toISOString();
}

function mockProposals(fileName: string): AgentProposal[] {
  const base = {
    recordType: "",
    source: { kind: "app", app: "演示导出" },
    evidence: { file: fileName, locator: "row 2" },
    payload: {},
    createdAt: new Date().toISOString(),
  };
  const make = (
    index: number,
    kind: string,
    value: unknown,
    unit: string,
    startAt: string,
    endAt: string | null,
    confidence: number,
    locator: string,
    extra: Partial<AgentProposal> = {},
  ): AgentProposal => ({
    ...base,
    ...extra,
    id: `prp_mock_${index}`,
    kind,
    recordType: `org.eclipsehealth.health.${kind}`,
    value,
    unit,
    startAt,
    endAt,
    durationSec:
      endAt !== null
        ? Math.max(0, (Date.parse(endAt) - Date.parse(startAt)) / 1000)
        : null,
    confidence,
    evidence: { file: fileName, locator },
    fingerprint: `mock-${index}`,
  });

  return [
    make(1, "steps", 8421, "count", iso(60 * 20), null, 0.92, "line 12"),
    make(2, "heart-rate", 72, "count/min", iso(60 * 5), null, 0.96, "line 24"),
    make(3, "resting-heart-rate", 58, "count/min", iso(60 * 8), null, 0.9, "line 31"),
    make(
      4,
      "sleep",
      "asleep-core",
      "1",
      iso(60 * 9),
      iso(60 * 8 - 25),
      0.88,
      "line 40",
    ),
    make(5, "spo2", 97, "%", iso(60 * 4), null, 0.93, "line 52"),
    make(
      6,
      "blood-pressure",
      { systolic: 118, diastolic: 76 },
      "mm[Hg]",
      iso(60 * 6),
      null,
      0.95,
      "line 61",
    ),
    make(
      7,
      "workout",
      {
        activity: "running",
        durationSec: 1800,
        distanceM: 4200,
        energyKcal: 280,
        avgHeartRate: 148,
      },
      "1",
      iso(60 * 26),
      iso(60 * 26 - 30),
      0.94,
      "line 70",
    ),
    make(8, "stress", 32, "1", iso(60 * 3), null, 0.82, "line 80"),
    make(9, "respiratory-rate", 15, "count/min", iso(60 * 30), null, 0.87, "line 88"),
    make(10, "body-temperature", 36.6, "Cel", iso(60 * 10), null, 0.91, "line 96"),
    make(11, "blood-glucose", 5.4, "mmol/L", iso(60 * 12), null, 0.89, "line 104"),
    make(
      12,
      "hrv",
      { metric: "rmssd", value: 42 },
      "ms",
      iso(60 * 7),
      null,
      0.86,
      "line 112",
    ),
    make(13, "body-mass", 68.4, "kg", iso(60 * 48), null, 0.97, "line 120"),
  ];
}

async function mockRun(
  sessionId: string,
  options: AgentRunOptions,
): Promise<void> {
  const entry = mockSessions.get(sessionId);
  if (!entry) {
    options.onError?.({
      code: "session_not_found",
      message: "导入会话不存在或已过期",
    });
    return;
  }
  const fileName = entry.files[0]?.name ?? "export.csv";
  const proposals = mockProposals(fileName);
  const started = Date.now();
  const push = (name: string, args: Record<string, unknown>, index: number) =>
    options.onToolCall?.({ id: `call_${index}`, name, args, index });

  try {
    entry.session.status = "running";
    options.onStatus?.({
      phase: "starting",
      provider: "mock",
      files: entry.files.length,
      limits: { maxFiles: 20, maxToolCalls: 12, network: false },
      toolCalls: 0,
      elapsedMs: 0,
      network: false,
    });
    await sleep(320, options.signal);

    push("list_files", {}, 1);
    await sleep(260, options.signal);
    options.onToolResult?.({
      id: "call_1",
      name: "list_files",
      ok: true,
      durationMs: 30,
      resultSummary: `${entry.files.length} 个文件`,
    });
    options.onToken?.("已读取文件清单，正在检查表头与时间列…");
    await sleep(200, options.signal);

    push("read_text_file", { path: fileName, limit: 4096 }, 2);
    await sleep(260, options.signal);
    options.onToolResult?.({
      id: "call_2",
      name: "read_text_file",
      ok: true,
      durationMs: 45,
      resultSummary: "读取 4096 字节",
    });

    push("write_script", { name: "parse.py", code: "import csv\n..." }, 3);
    await sleep(240, options.signal);
    push("run_python", { script: "parse.py" }, 4);
    await sleep(420, options.signal);
    options.onToolResult?.({
      id: "call_4",
      name: "run_python",
      ok: true,
      durationMs: 380,
      resultSummary: `产出 ${proposals.length} 条候选`,
    });

    push("propose_records", { records: proposals.length }, 5);
    entry.proposals = proposals;
    entry.session.proposalCount = proposals.length;
    options.onPreview?.({
      count: proposals.length,
      total: proposals.length,
      items: proposals.slice(0, 50),
      issues: [],
    });
    await sleep(220, options.signal);

    push("finish", { summary: "识别出 13 类健康数据" }, 6);
    options.onToolResult?.({
      id: "call_6",
      name: "finish",
      ok: true,
      durationMs: 10,
      resultSummary: "完成",
    });
    entry.session.status = "ready";
    entry.session.summary = "识别出 13 类健康数据";
    options.onStatus?.({
      phase: "ready",
      provider: "mock",
      files: entry.files.length,
      toolCalls: 6,
      elapsedMs: Date.now() - started,
      network: false,
    });
    options.onDone?.({
      summary: "识别出 13 类健康数据",
      proposalCount: proposals.length,
      toolCalls: 6,
      durationMs: Date.now() - started,
      status: "ready",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      options.onError?.({ code: "cancelled", message: "已停止解析" });
      return;
    }
    options.onError?.({ code: "mock_failed", message: "演示解析失败" });
  }
}

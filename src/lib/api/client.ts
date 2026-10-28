import { mockAnalysis, mockDelay, mockHealth, mockRecords } from "./mock";
import type {
  AnalysisSummary,
  HealthStatus,
  RecordSummary,
} from "./types";

const DEFAULT_BASE_URL = "http://127.0.0.1:8765/api/v1";
const REQUEST_TIMEOUT_MS = 8_000;

const baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL;
const mockFlag = import.meta.env.VITE_USE_MOCK;
const useMock = mockFlag === undefined || mockFlag === ""
  ? import.meta.env.DEV
  : mockFlag === "true";

export class ApiError extends Error {
  readonly status: number | undefined;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : "network request failed",
    );
  }

  if (!response.ok) {
    throw new ApiError(`GET ${path} failed`, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: (): Promise<HealthStatus> =>
    useMock ? mockDelay(mockHealth) : request<HealthStatus>("/health"),

  records: {
    list: (params?: { limit?: number }): Promise<RecordSummary[]> => {
      if (useMock) {
        const limit = params?.limit ?? mockRecords.length;
        return mockDelay(mockRecords.slice(0, limit));
      }
      const query = params?.limit ? `?limit=${params.limit}` : "";
      return request<RecordSummary[]>(`/records${query}`);
    },

    get: (id: string): Promise<RecordSummary> => {
      if (useMock) {
        const found = mockRecords.find((record) => record.id === id);
        return found
          ? mockDelay(found)
          : Promise.reject(new ApiError("record not found", 404));
      }
      return request<RecordSummary>(`/records/${encodeURIComponent(id)}`);
    },

    analysis: (recordId: string): Promise<AnalysisSummary> => {
      if (useMock) {
        return mockDelay(mockAnalysis);
      }
      return request<AnalysisSummary>(
        `/records/${encodeURIComponent(recordId)}/analysis`,
      );
    },
  },
};

export const apiMode = { mock: useMock, baseUrl } as const;

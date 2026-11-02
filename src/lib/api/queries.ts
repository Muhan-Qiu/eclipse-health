import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, fetchRecordCompare, fetchScores, fetchSuggestions, fetchTrends } from "./client";
import type { TrendsParams } from "./client";
import { isRetryableNetworkError } from "./error";
import { toRecordSummary } from "./adapters";
import type { RecordListParams } from "./contract";
import type {
  AnalysisResult,
  AnalysisStartBody,
  HealthRecord,
  RecordPage,
  RecordSummary,
} from "./types";

export const queryKeys = {
  records: (params?: RecordListParams) => ["records", params ?? {}] as const,
  healthRecords: (params?: RecordListParams) =>
    ["health-records", params ?? {}] as const,
  record: (id: string) => ["record", id] as const,
  signals: (id: string) => ["signals", id] as const,
  signal: (id: string, lead?: string) => ["signal", id, lead ?? ""] as const,
  recordAnalyses: (id: string) => ["record-analyses", id] as const,
  analysis: (id: string) => ["analysis", id] as const,
  engine: ["engine"] as const,
  members: ["members"] as const,
  trends: (params: TrendsParams) => ["trends", params] as const,
  compare: (ids: string[]) => ["compare", ids] as const,
  scores: ["scores"] as const,
  suggestions: ["suggestions"] as const,
};

const retryNetwork = (failureCount: number, error: unknown) =>
  isRetryableNetworkError(error) && failureCount < 2;

export interface RecordListResult {
  items: RecordSummary[];
  total: number;
  limit: number;
  offset: number;
}

export function useRecords(params: RecordListParams) {
  return useQuery({
    queryKey: queryKeys.records(params),
    queryFn: async (): Promise<RecordListResult> => {
      const page = await api.records.list(params);
      return {
        items: page.items.map((record) => toRecordSummary(record)),
        total: page.total,
        limit: page.limit,
        offset: page.offset,
      };
    },
    staleTime: 15_000,
    retry: retryNetwork,
  });
}

/** 健康数据页需要完整 payload，因此返回原始 HealthRecord，而不是 RecordSummary。 */
export function useHealthRecords(params: RecordListParams) {
  return useQuery({
    queryKey: queryKeys.healthRecords(params),
    queryFn: (): Promise<RecordPage> => api.records.list(params),
    // 导入流程不经过 react-query，回到本页/窗口重新聚焦时总是取最新数量。
    staleTime: 0,
    retry: retryNetwork,
  });
}

export function useRecord(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.record(id ?? ""),
    queryFn: () => api.records.get(id ?? ""),
    enabled: Boolean(id),
    staleTime: 15_000,
    retry: retryNetwork,
  });
}

export function useRecordSignals(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.signals(id ?? ""),
    queryFn: () => api.records.signals(id ?? ""),
    enabled: Boolean(id),
    staleTime: 60_000,
    retry: retryNetwork,
  });
}

export function useSignal(id: string | undefined, lead: string | undefined) {
  return useQuery({
    queryKey: queryKeys.signal(id ?? "", lead),
    queryFn: () => api.records.signal(id ?? "", lead),
    enabled: Boolean(id) && Boolean(lead),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 10 * 60_000,
    retry: retryNetwork,
  });
}

export function useRecordAnalyses(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.recordAnalyses(id ?? ""),
    queryFn: () => api.records.analyses(id ?? ""),
    enabled: Boolean(id),
    staleTime: 5_000,
    retry: retryNetwork,
    refetchInterval: (query) => {
      const latest = query.state.data?.items[0];
      return latest && (latest.status === "queued" || latest.status === "running")
        ? 1_200
        : false;
    },
  });
}

export function useAnalysis(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.analysis(id ?? ""),
    queryFn: () => api.analyses.get(id ?? "", true),
    enabled: Boolean(id) && enabled,
    staleTime: 0,
    gcTime: 10 * 60_000,
    retry: retryNetwork,
    refetchInterval: (query) => {
      const analysis = query.state.data as AnalysisResult | undefined;
      return analysis &&
        (analysis.status === "queued" || analysis.status === "running")
        ? 1_000
        : false;
    },
  });
}

export function useEngineStatus() {
  return useQuery({
    queryKey: queryKeys.engine,
    queryFn: () => api.engine.status(),
    staleTime: 5_000,
    retry: retryNetwork,
    refetchInterval: (query) =>
      query.state.data?.status === "warming" ? 2_500 : false,
  });
}

export function useMembers() {
  return useQuery({
    queryKey: queryKeys.members,
    queryFn: () => api.members.list(),
    staleTime: 5 * 60_000,
    retry: retryNetwork,
  });
}

export function useTrends(params: TrendsParams) {
  return useQuery({
    queryKey: queryKeys.trends(params),
    queryFn: () => fetchTrends(params),
    staleTime: 30_000,
    retry: retryNetwork,
  });
}

export function useRecordCompare(ids: string[]) {
  const unique = [...new Set(ids)];
  return useQuery({
    queryKey: queryKeys.compare(unique),
    queryFn: () => fetchRecordCompare(unique),
    enabled: unique.length >= 2 && unique.length <= 4,
    staleTime: 30_000,
    retry: retryNetwork,
  });
}

export function useStartAnalysis(recordId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AnalysisStartBody = {}) =>
      api.records.startAnalysis(recordId ?? "", body),
    onSuccess: () => {
      if (!recordId) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recordAnalyses(recordId),
      });
      void queryClient.invalidateQueries({ queryKey: ["records"] });
      void queryClient.invalidateQueries({ queryKey: ["trends"] });
    },
  });
}

/** 取消排队/运行中的分析：运行中会中断引擎，队列立即继续。 */
export function useCancelAnalysis(recordId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (analysisId: string) => api.analyses.cancel(analysisId),
    onSuccess: () => {
      if (!recordId) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recordAnalyses(recordId),
      });
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    },
  });
}

export function useDeleteRecord(recordId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.records.delete(recordId ?? ""),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.record(recordId ?? "") });
      void queryClient.invalidateQueries({ queryKey: ["trends"] });
      void queryClient.invalidateQueries({ queryKey: ["compare"] });
    },
  });
}

/** D1：收藏切换，先改本地列表再对齐后端。 */
export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, favorite }: { id: string; favorite: boolean }) =>
      api.records.updateFavorite(id, favorite),
    onMutate: async ({ id, favorite }) => {
      await queryClient.cancelQueries({ queryKey: ["records"] });
      queryClient.setQueriesData<RecordListResult>(
        { queryKey: ["records"] },
        (previous) =>
          previous
            ? {
                ...previous,
                items: previous.items.map((item) =>
                  item.id === id ? { ...item, favorite } : item,
                ),
              }
            : previous,
      );
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    },
    onSettled: (_data, _error, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.record(variables.id),
      });
    },
  });
}

/** A1：一键载入内置 MIT-BIH 示例，并在后台发起分析。 */
export function useImportSample() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.imports.sample("mitdb-100", { startAnalysis: true }),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.record(result.recordId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recordAnalyses(result.recordId),
      });
    },
  });
}

/** 仪表盘指标：取最近几条记录的分析，找最新一条完成的。 */
export function useRecentAnalyses(records: RecordSummary[] | undefined) {
  const ids = (records ?? []).slice(0, 5).map((record) => record.id);
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: queryKeys.recordAnalyses(id),
      queryFn: () => api.records.analyses(id),
      staleTime: 30_000,
      retry: retryNetwork,
    })),
  });
}

/**
 * 首页评分/建议：后端未提供（404）或未启动时保持静默，
 * 页面据此隐藏或显示轻量的「数据不足」，而不是红屏。
 */
export function useHealthScores() {
  return useQuery({
    queryKey: queryKeys.scores,
    queryFn: () => fetchScores(),
    staleTime: 60_000,
    retry: retryNetwork,
  });
}

export function useHealthSuggestions() {
  return useQuery({
    queryKey: queryKeys.suggestions,
    queryFn: () => fetchSuggestions(),
    staleTime: 60_000,
    retry: retryNetwork,
  });
}

export function recordToSummary(record: HealthRecord): RecordSummary {
  return toRecordSummary(record);
}

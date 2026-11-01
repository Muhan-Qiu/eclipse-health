import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMock } from "@/lib/api/client";
import { dashboardCardsApi, type CardPatch } from "./api";
import type { CardCreateInput } from "./types";

const EMPTY_CARDS = [] as const;
const EMPTY_TEMPLATES = [] as const;
const EMPTY_DRAFTS = [] as const;

export const dashboardCardKeys = {
  cards: (memberId?: string) => ["dashboard", "cards", memberId ?? ""] as const,
  templates: ["dashboard", "card-templates"] as const,
  drafts: (memberId?: string) =>
    ["dashboard", "card-drafts", memberId ?? ""] as const,
};

/** 自定义卡片及其数据（`includeData=true` 一次取回，避免 N+1）。 */
export function useDashboardCards(memberId: string | undefined) {
  const query = useQuery({
    queryKey: dashboardCardKeys.cards(memberId),
    queryFn: () => dashboardCardsApi.list(memberId),
    enabled: !useMock,
    retry: 0,
    staleTime: 10_000,
  });
  return {
    cards: query.data ?? EMPTY_CARDS,
    isLoading: query.isLoading,
    isError: query.isError,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
  };
}

export function useCardTemplates() {
  const query = useQuery({
    queryKey: dashboardCardKeys.templates,
    queryFn: dashboardCardsApi.templates,
    enabled: !useMock,
    retry: 0,
    staleTime: Number.POSITIVE_INFINITY,
  });
  return {
    templates: query.data ?? EMPTY_TEMPLATES,
  };
}

/**
 * 助手草稿：从助手页回到仪表盘时自动刷新；打开仪表盘期间每 10 秒轮询一次，
 * 这样助手刚生成的草稿不用手动刷新就会出现。
 */
export function useCardDrafts(memberId: string | undefined) {
  const query = useQuery({
    queryKey: dashboardCardKeys.drafts(memberId),
    queryFn: () => dashboardCardsApi.drafts(memberId),
    enabled: !useMock,
    retry: 0,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 10_000,
  });
  return {
    drafts: query.data ?? EMPTY_DRAFTS,
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
}

function useInvalidateDashboard() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["dashboard", "cards"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard", "card-drafts"] });
  };
}

export function useCreateDashboardCard(memberId: string | undefined) {
  const invalidate = useInvalidateDashboard();
  return useMutation({
    mutationFn: (input: CardCreateInput) =>
      dashboardCardsApi.create({ ...input, memberId }),
    onSuccess: invalidate,
  });
}

export function useUpdateDashboardCard(memberId: string | undefined) {
  const invalidate = useInvalidateDashboard();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: CardPatch }) =>
      dashboardCardsApi.update(id, patch, memberId),
    onSuccess: invalidate,
  });
}

export function useDeleteDashboardCard(memberId: string | undefined) {
  const invalidate = useInvalidateDashboard();
  return useMutation({
    mutationFn: (id: string) => dashboardCardsApi.remove(id, memberId),
    onSuccess: invalidate,
  });
}

export function useConfirmCardDraft(memberId: string | undefined) {
  const invalidate = useInvalidateDashboard();
  return useMutation({
    mutationFn: (draftId: string) =>
      dashboardCardsApi.confirmDraft(draftId, memberId),
    onSuccess: invalidate,
  });
}

export function useDiscardCardDraft(memberId: string | undefined) {
  const invalidate = useInvalidateDashboard();
  return useMutation({
    mutationFn: (draftId: string) =>
      dashboardCardsApi.discardDraft(draftId, memberId),
    onSuccess: invalidate,
  });
}

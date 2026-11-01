import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isRetryableNetworkError } from "@/lib/api/error";
import { queryKeys, useMembers } from "@/lib/api/queries";
import type { Member } from "@/lib/api/types";
import {
  createExercise,
  createMetric,
  deleteExercise,
  deleteMetric,
  getMemory,
  listExercises,
  listMetrics,
  putMemory,
  updateMember,
  updateMetric,
} from "./api";
import type { ExerciseListParams } from "./api";
import type {
  ExerciseInput,
  MemberPatch,
  MetricInput,
  MetricListParams,
  MetricPatch,
} from "./types";

export const metricKeys = {
  list: (params: MetricListParams) => ["metrics", params] as const,
};

export function useMetrics(params: MetricListParams) {
  return useQuery({
    queryKey: metricKeys.list(params),
    queryFn: () => listMetrics(params),
    staleTime: 15_000,
    retry: (failureCount, error) =>
      isRetryableNetworkError(error) && failureCount < 2,
  });
}

function useInvalidateMetrics() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["metrics"] });
    void queryClient.invalidateQueries({ queryKey: ["records"] });
  };
}

export function useCreateMetric() {
  const invalidate = useInvalidateMetrics();
  return useMutation({
    mutationFn: (input: MetricInput) => createMetric(input),
    onSuccess: invalidate,
  });
}

export function useUpdateMetric() {
  const invalidate = useInvalidateMetrics();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: MetricPatch }) =>
      updateMetric(id, patch),
    onSuccess: invalidate,
  });
}

export function useDeleteMetric() {
  const invalidate = useInvalidateMetrics();
  return useMutation({
    mutationFn: (id: string) => deleteMetric(id),
    onSuccess: invalidate,
  });
}

export function useUpdateMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
      current,
    }: {
      id: string;
      patch: MemberPatch;
      current?: Member;
    }) => updateMember(id, patch, current),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.members });
    },
  });
}

export const exerciseKeys = {
  list: (params: ExerciseListParams) => ["exercises", params] as const,
};

export function useExercises(params: ExerciseListParams) {
  return useQuery({
    queryKey: exerciseKeys.list(params),
    queryFn: () => listExercises(params),
    staleTime: 15_000,
    retry: (failureCount, error) =>
      isRetryableNetworkError(error) && failureCount < 2,
  });
}

function useInvalidateExercises() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["exercises"] });
    void queryClient.invalidateQueries({ queryKey: ["records"] });
  };
}

export function useCreateExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (input: ExerciseInput) => createExercise(input),
    onSuccess: invalidate,
  });
}

export function useDeleteExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (id: string) => deleteExercise(id),
    onSuccess: invalidate,
  });
}

export const memoryKeys = {
  document: ["memory"] as const,
};

export function useMemory() {
  return useQuery({
    queryKey: memoryKeys.document,
    queryFn: () => getMemory(),
    staleTime: 15_000,
    retry: (failureCount, error) =>
      isRetryableNetworkError(error) && failureCount < 2,
  });
}

export function useUpdateMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { content: string; enabled: boolean }) => putMemory(input),
    onSuccess: (document) => {
      queryClient.setQueryData(memoryKeys.document, document);
    },
  });
}

export { useMembers };

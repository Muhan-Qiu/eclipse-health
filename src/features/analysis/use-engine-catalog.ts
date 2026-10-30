import { useQuery } from "@tanstack/react-query";
import { isRetryableNetworkError } from "@/lib/api/error";
import { fetchEngineCatalog } from "./engine-catalog";

export const engineCatalogQueryKey = ["analysis", "engines"] as const;

/** 引擎目录：变化很少，缓存一分钟；断网时最多重试两次。 */
export function useEngineCatalog() {
  return useQuery({
    queryKey: engineCatalogQueryKey,
    queryFn: ({ signal }) => fetchEngineCatalog(signal),
    staleTime: 60_000,
    retry: (failureCount, error) =>
      isRetryableNetworkError(error) && failureCount < 2,
  });
}

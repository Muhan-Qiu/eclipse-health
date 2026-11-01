import { useQuery } from "@tanstack/react-query";
import { MODULE_CONTRIBUTIONS_KEY, listContributions } from "../api";
import type { ModuleWidget } from "../types";

const EMPTY_WIDGETS: ModuleWidget[] = [];

export interface ModuleWidgetsState {
  widgets: ModuleWidget[];
  isLoading: boolean;
  isError: boolean;
  /** 首次成功后才允许按当前模块清理/合并布局。 */
  isSuccess: boolean;
  refetch: () => void;
}

/**
 * 仪表盘与布局编辑器共用的模块卡片列表。
 *
 * 不再按演示模式短路：布局需要知道卡片是否已经加载完成，才能安全地
 * 合并/清理已保存的模块卡片顺序；错误由调用方决定是否展示。
 */
export function useModuleWidgets(): ModuleWidgetsState {
  const query = useQuery({
    queryKey: MODULE_CONTRIBUTIONS_KEY,
    queryFn: () => listContributions(),
    // 卡片失败不阻塞仪表盘；用户可在错误提示里手动重试。
    retry: 0,
    staleTime: 30_000,
  });

  return {
    widgets: query.data?.widgets ?? EMPTY_WIDGETS,
    isLoading: query.isLoading,
    isError: query.isError,
    isSuccess: query.isSuccess,
    refetch: () => {
      void query.refetch();
    },
  };
}

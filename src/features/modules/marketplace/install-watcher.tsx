import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { marketplaceErrorMessage } from "./api";

interface InstallDoneDetail {
  moduleId: string;
  name: string;
}

interface InstallErrorDetail extends InstallDoneDetail {
  error: unknown;
}

/**
 * 后台模块安装的全局通知：安装任务在 API 层继续轮询，即使用户关闭弹窗或离开
 * 模块页也不会中断；完成/失败时刷新模块列表并提示。
 */
export function ModuleInstallWatcher() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  useEffect(() => {
    const onDone = (event: Event) => {
      const detail = (event as CustomEvent<InstallDoneDetail>).detail;
      if (!detail) return;
      void queryClient.invalidateQueries({ queryKey: ["modules"] });
      void queryClient.invalidateQueries({ queryKey: ["marketplace"] });
      toast.success(
        t("moduleUi.marketplace.toast.installed", { name: detail.name }),
      );
    };
    const onError = (event: Event) => {
      const detail = (event as CustomEvent<InstallErrorDetail>).detail;
      if (!detail) return;
      toast.error(t("moduleUi.marketplace.details.installFailed"), {
        description: marketplaceErrorMessage(detail.error, t),
      });
    };
    window.addEventListener("eh:module-install-done", onDone);
    window.addEventListener("eh:module-install-error", onError);
    return () => {
      window.removeEventListener("eh:module-install-done", onDone);
      window.removeEventListener("eh:module-install-error", onError);
    };
  }, [queryClient, t]);

  return null;
}

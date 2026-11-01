import "./i18n";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, ArrowUpCircle, PackagePlus } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import {
  MODULE_AUDIT_KEY,
  MODULE_CONTRIBUTIONS_KEY,
  MODULE_QUERY_KEY,
  disableModule,
  enableModule,
  listModules,
  startModule,
  stopModule,
  uninstallModule,
} from "./api";
import { AuditPanel } from "./audit-panel";
import { moduleErrorMessage } from "./errors";
import { InstallDialog } from "./install-dialog";
import {
  MARKETPLACE_UPDATES_KEY,
  getMarketplaceUpdates,
} from "./marketplace/api";
import type { MarketplaceTab } from "./marketplace/types";
import { ModuleDetail } from "./module-detail";
import { ModuleList, type ModuleAction } from "./module-list";
import { UninstallDialog } from "./uninstall-dialog";
import type { ModuleSummary } from "./types";

const TOAST_KEYS: Record<ModuleAction, string> = {
  start: "moduleUi.toast.started",
  stop: "moduleUi.toast.stopped",
  enable: "moduleUi.toast.enabled",
  disable: "moduleUi.toast.disabled",
};

function runAction(moduleId: string, action: ModuleAction): Promise<ModuleSummary> {
  switch (action) {
    case "start":
      return startModule(moduleId);
    case "stop":
      return stopModule(moduleId);
    case "enable":
      return enableModule(moduleId);
    case "disable":
      return disableModule(moduleId);
  }
}

export function ModulesWorkspace() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [installOpen, setInstallOpen] = useState(false);
  const [installTab, setInstallTab] = useState<MarketplaceTab>("official");
  const [detailId, setDetailId] = useState<string | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<ModuleSummary | null>(null);

  const [auditModuleId, setAuditModuleId] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditRefreshToken, setAuditRefreshToken] = useState(0);

  const modulesQuery = useQuery({
    queryKey: MODULE_QUERY_KEY,
    queryFn: listModules,
  });
  const modules = modulesQuery.data ?? [];

  // 市场未配置/后端版本较旧时静默隐藏更新提示，不影响模块页主体。
  const updatesQuery = useQuery({
    queryKey: MARKETPLACE_UPDATES_KEY,
    queryFn: getMarketplaceUpdates,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const updates = updatesQuery.isError ? [] : (updatesQuery.data ?? []);

  function refreshAll() {
    // ["modules"] 覆盖 manifest/audit/contributions/page-contributions 等子键；
    // 单独再失效 contributions，避免未来子键改名后首页卡片与模块页漏刷。
    void queryClient.invalidateQueries({ queryKey: MODULE_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_CONTRIBUTIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_AUDIT_KEY });
    void queryClient.invalidateQueries({ queryKey: MARKETPLACE_UPDATES_KEY });
    setAuditRefreshToken((value) => value + 1);
  }

  function openInstall(tab: MarketplaceTab) {
    setInstallTab(tab);
    setInstallOpen(true);
  }

  const actionMutation = useMutation({
    mutationFn: ({ module, action }: { module: ModuleSummary; action: ModuleAction }) =>
      runAction(module.id, action),
    onSuccess: (_data, variables) => {
      toast.success(t(TOAST_KEYS[variables.action], { name: variables.module.name }));
      refreshAll();
    },
    onError: (error) => {
      toast.error(t("moduleUi.toast.actionFailed"), {
        description: moduleErrorMessage(error, t),
      });
      refreshAll();
    },
  });

  const uninstallMutation = useMutation({
    mutationFn: ({
      module,
      keepData,
    }: {
      module: ModuleSummary;
      keepData: boolean;
    }) => uninstallModule(module.id, keepData),
    onSuccess: (_data, variables) => {
      const key = variables.keepData
        ? "moduleUi.uninstall.doneKept"
        : "moduleUi.uninstall.doneDeleted";
      toast.success(t(key, { name: variables.module.name }));
      setUninstallTarget(null);
      if (detailId === variables.module.id) setDetailId(null);
      refreshAll();
    },
    onError: (error) => {
      toast.error(t("moduleUi.toast.actionFailed"), {
        description: moduleErrorMessage(error, t),
      });
    },
  });

  const detailModule = modules.find((module) => module.id === detailId) ?? null;
  const actionBusy = actionMutation.isPending
    ? {
        moduleId: actionMutation.variables?.module.id ?? "",
        action: actionMutation.variables?.action ?? "",
      }
    : null;

  return (
    <>
      <PageHeader
        eyebrow={t("modules.eyebrow")}
        title={t("modules.title")}
        description={t("modules.description")}
        actions={
          <Button type="button" onClick={() => openInstall("official")}>
            <PackagePlus aria-hidden="true" />
            {t("moduleUi.install")}
          </Button>
        }
      />

      {modulesQuery.isError ? (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("moduleUi.loadError")}</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{t("moduleUi.loadErrorDesc")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void modulesQuery.refetch()}
            >
              {t("common.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {updates.length > 0 ? (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <ArrowUpCircle className="size-4" aria-hidden="true" />
              {t("moduleUi.marketplace.updates.title")}
            </CardTitle>
            <CardDescription>
              {t("moduleUi.marketplace.updates.description", {
                count: updates.length,
              })}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y divide-border border-t border-border">
              {updates.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">{item.name}</span>
                      <Badge className="font-normal">
                        {t("moduleUi.marketplace.updateBadge")}
                      </Badge>
                      <span className="eh-caption text-muted-foreground">
                        v{item.installedVersion} → v{item.availableVersion}
                      </span>
                    </div>
                    <code className="eh-caption block truncate text-muted-foreground">
                      {item.id}
                    </code>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openInstall(item.source ?? "official")}
                  >
                    {t("moduleUi.marketplace.updates.button")}
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <ModuleList
        modules={modules}
        loading={modulesQuery.isLoading}
        busy={actionBusy}
        onAction={(module, action) => actionMutation.mutate({ module, action })}
        onDetails={(module) => setDetailId(module.id)}
        onUninstall={(module) => setUninstallTarget(module)}
        onRefresh={() => void modulesQuery.refetch()}
      />

      <div id="module-audit">
        <AuditPanel
          modules={modules}
          moduleId={auditModuleId}
          action={auditAction}
          onModuleChange={setAuditModuleId}
          onActionChange={setAuditAction}
          refreshToken={auditRefreshToken}
        />
      </div>

      <InstallDialog
        open={installOpen}
        installed={modules}
        initialTab={installTab}
        onClose={() => setInstallOpen(false)}
        onInstalled={refreshAll}
      />

      <ModuleDetail
        module={detailModule}
        open={detailModule !== null}
        onClose={() => setDetailId(null)}
        onChanged={refreshAll}
        onViewAudit={(moduleId) => {
          setAuditModuleId(moduleId);
          setDetailId(null);
          document.getElementById("module-audit")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }}
      />

      <UninstallDialog
        open={uninstallTarget !== null}
        module={uninstallTarget}
        busy={uninstallMutation.isPending}
        onClose={() => {
          if (!uninstallMutation.isPending) setUninstallTarget(null);
        }}
        onConfirm={(keepData) => {
          if (uninstallTarget) {
            uninstallMutation.mutate({ module: uninstallTarget, keepData });
          }
        }}
      />
    </>
  );
}

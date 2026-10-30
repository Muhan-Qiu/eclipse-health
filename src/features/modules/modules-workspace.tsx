import "./i18n";

import { useRef, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Upload } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/page-header";
import {
  MODULE_AUDIT_KEY,
  MODULE_QUERY_KEY,
  disableModule,
  enableModule,
  installModulePackage,
  listModules,
  previewModulePackage,
  startModule,
  stopModule,
  uninstallModule,
} from "./api";
import { AuditPanel } from "./audit-panel";
import { moduleErrorMessage } from "./errors";
import { InstallDialog } from "./install-dialog";
import { ModuleDetail } from "./module-detail";
import { ModuleList, type ModuleAction } from "./module-list";
import { UninstallDialog } from "./uninstall-dialog";
import type { ModulePreview, ModuleSummary } from "./types";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ModulePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [installBusy, setInstallBusy] = useState(false);

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

  function refreshAll() {
    void queryClient.invalidateQueries({ queryKey: MODULE_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_AUDIT_KEY });
    setAuditRefreshToken((value) => value + 1);
  }

  async function loadPreview(file: File) {
    setPreviewLoading(true);
    setPreviewError(null);
    setPreview(null);
    try {
      setPreview(await previewModulePackage(file));
    } catch (error) {
      setPreviewError(moduleErrorMessage(error, t));
    } finally {
      setPreviewLoading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".ehmod")) {
      toast.error(t("moduleUi.errors.invalidPackage"));
      return;
    }
    setPendingFile(file);
    void loadPreview(file);
  }

  function closeInstall() {
    if (installBusy) return;
    setPendingFile(null);
    setPreview(null);
    setPreviewError(null);
  }

  async function handleInstall(permissions: string[], enable: boolean) {
    if (!pendingFile) return;
    setInstallBusy(true);
    try {
      const installed = await installModulePackage(pendingFile, {
        permissions,
        enable,
      });
      const upgrading = preview?.alreadyInstalled === true;
      toast.success(
        upgrading
          ? t("moduleUi.installFlow.successUpgrade", {
              name: installed.name,
              version: installed.version,
            })
          : t("moduleUi.installFlow.success", { name: installed.name }),
      );
      setPendingFile(null);
      setPreview(null);
      refreshAll();
    } catch (error) {
      toast.error(t("moduleUi.toast.actionFailed"), {
        description: moduleErrorMessage(error, t),
      });
    } finally {
      setInstallBusy(false);
    }
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
          <Button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={installBusy}
          >
            <Upload aria-hidden="true" />
            {t("moduleUi.install")}
          </Button>
        }
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".ehmod,application/zip"
        className="sr-only"
        onChange={handleFileChange}
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
        open={pendingFile !== null}
        preview={preview}
        loading={previewLoading}
        error={previewError}
        busy={installBusy}
        onClose={closeInstall}
        onRetry={() => {
          if (pendingFile) void loadPreview(pendingFile);
        }}
        onConfirm={(permissions, enable) => void handleInstall(permissions, enable)}
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

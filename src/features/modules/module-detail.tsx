import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, ChevronRight, History, LayoutGrid, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  MODULE_AUDIT_KEY,
  MODULE_CONTRIBUTIONS_KEY,
  getModuleManifest,
  getPermissions,
  grantPermission,
  listAudit,
  revokePermission,
} from "./api";
import { AuditEventRow } from "./audit-row";
import { moduleErrorMessage } from "./errors";
import { ManifestFacts, ModuleIdentity } from "./manifest-summary";
import { permissionLabel } from "./permission-utils";
import { PermissionManager } from "./permission-list";
import "./pages/i18n";
import { PAGE_CONTRIBUTIONS_KEY, listPageContributions } from "./pages/page-api";
import { ModuleStateBadge } from "./state-badge";
import type { PermissionsState } from "./types";
import type { ModuleSummary } from "./types";

interface ModuleDetailProps {
  module: ModuleSummary | null;
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
  onViewAudit: (moduleId: string) => void;
}

export function ModuleDetail({
  module,
  open,
  onClose,
  onChanged,
  onViewAudit,
}: ModuleDetailProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const moduleId = module?.id ?? "";
  const enabled = open && Boolean(module);
  const [pendingRevoke, setPendingRevoke] = useState<string | null>(null);

  const manifestQuery = useQuery({
    queryKey: ["modules", "manifest", moduleId],
    queryFn: () => getModuleManifest(moduleId),
    enabled,
  });
  const permissionsQuery = useQuery({
    queryKey: ["modules", "permissions", moduleId],
    queryFn: () => getPermissions(moduleId),
    enabled,
  });
  const auditQuery = useQuery({
    queryKey: ["modules", "audit", "recent", moduleId],
    queryFn: () => listAudit({ moduleId, limit: 8 }),
    enabled,
  });
  const pagesQuery = useQuery({
    queryKey: PAGE_CONTRIBUTIONS_KEY,
    queryFn: listPageContributions,
    enabled,
    staleTime: 0,
  });
  const modulePages = (pagesQuery.data ?? []).filter(
    (page) => page.moduleId === moduleId,
  );

  function afterPermissionChange(state: PermissionsState) {
    queryClient.setQueryData(["modules", "permissions", moduleId], state);
    void queryClient.invalidateQueries({ queryKey: MODULE_AUDIT_KEY });
    // 授予/撤销 llm 会影响模块工具是否出现在助手目录，必须同步刷新贡献点。
    void queryClient.invalidateQueries({ queryKey: MODULE_CONTRIBUTIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: PAGE_CONTRIBUTIONS_KEY });
    onChanged();
  }

  const grant = useMutation({
    mutationFn: (scope: string) => grantPermission(moduleId, scope),
    onSuccess: (state, scope) => {
      afterPermissionChange(state);
      toast.success(t("moduleUi.toast.permissionGranted", { scope }));
    },
    onError: (error) => {
      toast.error(moduleErrorMessage(error, t));
    },
  });

  const revoke = useMutation({
    mutationFn: (scope: string) => revokePermission(moduleId, scope),
    onSuccess: (state, scope) => {
      afterPermissionChange(state);
      toast.success(t("moduleUi.toast.permissionRevoked", { scope }));
    },
    onError: (error) => {
      toast.error(moduleErrorMessage(error, t));
    },
  });

  const busyScope = grant.isPending
    ? grant.variables
    : revoke.isPending
      ? revoke.variables
      : null;

  const manifest = manifestQuery.data;
  const permissions = permissionsQuery.data;

  return (
    <>
      <Sheet
        open={open}
        onOpenChange={(next) => {
          if (!next) onClose();
        }}
      >
        <SheetContent side="right" className="w-full gap-0 sm:max-w-lg">
          <SheetHeader className="border-b border-border">
            <SheetTitle className="flex flex-wrap items-center gap-2">
              {module?.name ?? t("moduleUi.detail.title")}
              {module ? <ModuleStateBadge state={module.state} /> : null}
            </SheetTitle>
            <SheetDescription>
              {module
                ? t("moduleUi.detail.subtitle", {
                    id: module.id,
                    version: module.version,
                  })
                : t("moduleUi.detail.description")}
            </SheetDescription>
          </SheetHeader>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-4">
            {manifestQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : null}

            {manifestQuery.isError ? (
              <Alert variant="destructive">
                <AlertCircle aria-hidden="true" />
                <AlertTitle>{t("moduleUi.detail.loadError")}</AlertTitle>
                <AlertDescription>
                  {moduleErrorMessage(manifestQuery.error, t)}
                </AlertDescription>
              </Alert>
            ) : null}

            {manifest ? (
              <>
                <ModuleIdentity
                  name={manifest.name}
                  id={manifest.id}
                  version={manifest.version}
                  type={manifest.type}
                  description={manifest.description}
                  author={manifest.author}
                  license={manifest.license}
                  showCredits={false}
                />
                <ManifestFacts manifest={manifest} />
              </>
            ) : null}

            {modulePages.length > 0 ? (
              <section>
                <h4 className="eh-caption mb-2 flex items-center gap-1.5 text-muted-foreground">
                  <LayoutGrid className="size-3.5" aria-hidden="true" />
                  {t("modulePage.pagesTitle")}
                </h4>
                <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                  {modulePages.map((page) => (
                    <li key={page.id}>
                      <Link
                        to={`/modules/${encodeURIComponent(moduleId)}/pages/${encodeURIComponent(page.id)}`}
                        onClick={onClose}
                        className="flex items-center justify-between gap-2 px-3 py-2.5 text-sm transition-colors hover:bg-muted/50"
                      >
                        <span className="truncate font-medium">
                          {page.title}
                        </span>
                        <span className="eh-caption flex shrink-0 items-center gap-0.5 text-muted-foreground">
                          {t("modulePage.openPage")}
                          <ChevronRight className="size-3.5" aria-hidden="true" />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="eh-caption flex items-center gap-1.5 text-muted-foreground">
                  <ShieldCheck className="size-3.5" aria-hidden="true" />
                  {t("moduleUi.detail.permissions")}
                </h4>
                {permissions ? (
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    {t("moduleUi.permissions.grantedCount", {
                      granted: permissions.granted.length,
                      requested: permissions.requested.length,
                    })}
                  </Badge>
                ) : null}
              </div>
              {permissionsQuery.isLoading ? <Skeleton className="h-24 w-full" /> : null}
              {permissionsQuery.isError ? (
                <p className="eh-small text-muted-foreground">
                  {moduleErrorMessage(permissionsQuery.error, t)}
                </p>
              ) : null}
              {permissions ? (
                <>
                  <PermissionManager
                    permissions={permissions.scopes}
                    busyScope={busyScope}
                    onGrant={(scope) => grant.mutate(scope)}
                    onRevoke={(scope) => setPendingRevoke(scope)}
                  />
                  <p className="eh-caption mt-2 text-muted-foreground">
                    {t("moduleUi.detail.revokeWarning")}
                  </p>
                </>
              ) : null}
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="eh-caption flex items-center gap-1.5 text-muted-foreground">
                  <History className="size-3.5" aria-hidden="true" />
                  {t("moduleUi.detail.recentAudit")}
                </h4>
                {module ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    onClick={() => onViewAudit(module.id)}
                  >
                    {t("common.view")}
                  </Button>
                ) : null}
              </div>
              {auditQuery.isLoading ? <Skeleton className="h-20 w-full" /> : null}
              {auditQuery.isError ? (
                <p className="eh-small text-muted-foreground">
                  {moduleErrorMessage(auditQuery.error, t)}
                </p>
              ) : null}
              {auditQuery.data ? (
                auditQuery.data.events.length === 0 ? (
                  <p className="eh-small text-muted-foreground">
                    {t("moduleUi.detail.noAudit")}
                  </p>
                ) : (
                  <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                    {auditQuery.data.events.map((event) => (
                      <AuditEventRow key={event.id} event={event} />
                    ))}
                  </ul>
                )
              ) : null}
            </section>
          </div>
        </SheetContent>
      </Sheet>

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(next) => {
          if (!next) setPendingRevoke(null);
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("moduleUi.permissions.revokeConfirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("moduleUi.permissions.revokeConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {pendingRevoke && permissions ? (
            <p className="eh-caption text-muted-foreground">
              {permissionLabel(
                t,
                permissions.scopes.find((item) => item.scope === pendingRevoke) ??
                  pendingRevoke,
              )}
            </p>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (pendingRevoke) revoke.mutate(pendingRevoke);
                setPendingRevoke(null);
              }}
            >
              {t("moduleUi.permissions.revoke")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

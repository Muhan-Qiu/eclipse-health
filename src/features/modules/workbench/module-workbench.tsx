import "./i18n";
import "../i18n";

import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  Boxes,
  History,
  LayoutGrid,
  ListChecks,
  Loader2,
  Play,
  Power,
  PowerOff,
  RefreshCw,
  ShieldCheck,
  Square,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
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
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { intlLocale } from "@/lib/i18n";
import {
  MODULE_AUDIT_KEY,
  MODULE_CONTRIBUTIONS_KEY,
  MODULE_QUERY_KEY,
  disableModule,
  enableModule,
  getModuleManifest,
  getPermissions,
  grantPermission,
  listAudit,
  listContributions,
  listModules,
  revokePermission,
  startModule,
  stopModule,
} from "../api";
import { AuditEventRow } from "../audit-row";
import { moduleDisplayName } from "../copy";
import { moduleErrorMessage } from "../errors";
import { formatDateTime, moduleTypeLabel } from "../format";
import { moduleTypeIcon } from "../module-icon";
import { PermissionManager } from "../permission-list";
import { ModuleStateBadge } from "../state-badge";
import {
  PAGE_CONTRIBUTIONS_KEY,
  listPageContributions,
} from "../pages/page-api";
import type {
  ModuleManifest,
  ModuleSummary,
  PermissionsState,
} from "../types";
import {
  ToolRunner,
  normalizeToolContribution,
  type ModuleToolContribution,
} from "./tool-runner";
import { WidgetCard } from "../widgets/widget-card";

interface PageItem {
  id: string;
  title: string;
}

interface ModelEntry {
  id: string;
  name: string;
  task?: string;
  format?: string;
  limitations: string[];
  nonDiagnostic: boolean;
}

interface RecordTypeEntry {
  id: string;
  name: string;
}

type ModuleAction = "start" | "stop" | "enable" | "disable";

const TOAST_KEYS: Record<ModuleAction, string> = {
  start: "moduleUi.toast.started",
  stop: "moduleUi.toast.stopped",
  enable: "moduleUi.toast.enabled",
  disable: "moduleUi.toast.disabled",
};

function runAction(
  moduleId: string,
  action: ModuleAction,
): Promise<ModuleSummary> {
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 模块 disabled 时贡献点接口可能不返回页面，回退到 manifest 的声明。 */
function readManifestPages(manifest: ModuleManifest | undefined): PageItem[] {
  const ui = manifest?.contributes?.ui;
  if (!isRecord(ui) || !Array.isArray(ui.pages)) return [];
  return ui.pages.flatMap((entry) => {
    if (!isRecord(entry) || typeof entry.id !== "string" || !entry.id) {
      return [];
    }
    return [
      {
        id: entry.id,
        title: typeof entry.title === "string" ? entry.title : entry.id,
      },
    ];
  });
}

function readManifestTools(
  manifest: ModuleManifest | undefined,
  summary: ModuleSummary,
): ModuleToolContribution[] {
  const raw = manifest?.contributes?.tools;
  if (!Array.isArray(raw)) return [];
  const meta = {
    moduleId: summary.id,
    moduleName: summary.name,
    moduleVersion: summary.version,
    moduleType: summary.type,
  };
  return raw.flatMap((entry) => {
    const tool = normalizeToolContribution(entry, meta);
    return tool ? [tool] : [];
  });
}

function readModels(manifest: ModuleManifest | undefined): ModelEntry[] {
  const raw = manifest?.contributes?.models;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (!isRecord(entry) || typeof entry.id !== "string" || !entry.id) {
      return [];
    }
    const card = isRecord(entry.modelCard) ? entry.modelCard : {};
    return [
      {
        id: entry.id,
        name: typeof entry.name === "string" ? entry.name : entry.id,
        task: typeof entry.task === "string" ? entry.task : undefined,
        format: typeof entry.format === "string" ? entry.format : undefined,
        limitations: Array.isArray(card.limitations)
          ? card.limitations.filter(
              (item): item is string => typeof item === "string",
            )
          : [],
        nonDiagnostic: card.nonDiagnostic === true,
      },
    ];
  });
}

function readRecordTypes(
  manifest: ModuleManifest | undefined,
): RecordTypeEntry[] {
  const raw = manifest?.contributes?.recordTypes;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (!isRecord(entry) || typeof entry.id !== "string" || !entry.id) {
      return [];
    }
    return [
      {
        id: entry.id,
        name: typeof entry.name === "string" ? entry.name : entry.id,
      },
    ];
  });
}

function resourceLabels(
  t: TFunction,
  manifest: ModuleManifest | undefined,
): string[] {
  const resources = manifest?.resources;
  if (!resources) return [];
  const labels: string[] = [];
  if (typeof resources.memoryMb === "number") {
    labels.push(t("moduleUi.manifest.memory", { value: resources.memoryMb }));
  }
  if (typeof resources.cpu === "number") {
    labels.push(t("moduleUi.manifest.cpu", { value: resources.cpu }));
  }
  if (typeof resources.startupTimeoutMs === "number") {
    labels.push(
      t("moduleUi.manifest.startupTimeout", {
        value: resources.startupTimeoutMs,
      }),
    );
  }
  return labels;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="eh-caption text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words text-sm">{children}</dd>
    </div>
  );
}

function BackButton() {
  const { t } = useTranslation();
  return (
    <Button variant="outline" size="sm" asChild>
      <Link to="/modules">
        <ArrowLeft aria-hidden="true" />
        {t("moduleWorkbench.backToModules")}
      </Link>
    </Button>
  );
}

function WorkbenchSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <Skeleton className="h-32 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    </div>
  );
}

export function ModuleWorkbench() {
  const { moduleId = "" } = useParams<{ moduleId: string }>();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const locale = intlLocale(i18n.language);

  const modulesQuery = useQuery({
    queryKey: MODULE_QUERY_KEY,
    queryFn: listModules,
  });
  const manifestQuery = useQuery({
    queryKey: ["modules", "manifest", moduleId],
    queryFn: () => getModuleManifest(moduleId),
    enabled: Boolean(moduleId),
  });
  const pagesQuery = useQuery({
    queryKey: PAGE_CONTRIBUTIONS_KEY,
    queryFn: listPageContributions,
    staleTime: 0,
  });
  const toolsQuery = useQuery({
    queryKey: [...MODULE_CONTRIBUTIONS_KEY, "tools"],
    queryFn: () => listContributions("tools"),
    staleTime: 30_000,
  });
  const widgetsQuery = useQuery({
    queryKey: [...MODULE_CONTRIBUTIONS_KEY, "widgets"],
    queryFn: () => listContributions("widgets"),
    staleTime: 30_000,
  });
  const permissionsQuery = useQuery({
    queryKey: ["modules", "permissions", moduleId],
    queryFn: () => getPermissions(moduleId),
    enabled: Boolean(moduleId),
  });
  const auditQuery = useQuery({
    queryKey: ["modules", "audit", "recent", moduleId],
    queryFn: () => listAudit({ moduleId, limit: 8 }),
    enabled: Boolean(moduleId),
  });

  const summary =
    modulesQuery.data?.find((module) => module.id === moduleId) ?? null;
  const manifest = manifestQuery.data;
  const displayName = moduleDisplayName(
    i18n.language,
    moduleId,
    summary?.name ?? manifest?.name ?? moduleId,
  );

  function refreshAll() {
    void queryClient.invalidateQueries({ queryKey: MODULE_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_CONTRIBUTIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_AUDIT_KEY });
    void queryClient.invalidateQueries({ queryKey: PAGE_CONTRIBUTIONS_KEY });
  }

  function afterPermissionChange(state: PermissionsState) {
    queryClient.setQueryData(["modules", "permissions", moduleId], state);
    void queryClient.invalidateQueries({ queryKey: MODULE_CONTRIBUTIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: MODULE_QUERY_KEY });
  }

  const actionMutation = useMutation({
    mutationFn: ({ action }: { action: ModuleAction }) =>
      runAction(moduleId, action),
    onSuccess: (_data, variables) => {
      toast.success(t(TOAST_KEYS[variables.action], { name: displayName }));
      refreshAll();
    },
    onError: (error) => {
      toast.error(t("moduleWorkbench.actionFailed"), {
        description: moduleErrorMessage(error, t),
      });
    },
  });

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

  if (modulesQuery.isPending) return <WorkbenchSkeleton />;

  if (modulesQuery.isError) {
    return (
      <>
        <PageHeader
          eyebrow={t("moduleWorkbench.eyebrow")}
          title={t("moduleWorkbench.loadError")}
          description={t("moduleWorkbench.loadErrorDesc")}
          actions={<BackButton />}
        />
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("moduleWorkbench.loadError")}</AlertTitle>
          <AlertDescription>{t("moduleWorkbench.loadErrorDesc")}</AlertDescription>
        </Alert>
        <div className="mt-4">
          <Button variant="outline" onClick={() => void modulesQuery.refetch()}>
            <RefreshCw aria-hidden="true" />
            {t("common.retry")}
          </Button>
        </div>
      </>
    );
  }

  if (!summary) {
    return (
      <EmptyState
        icon={Boxes}
        title={t("moduleWorkbench.missingTitle")}
        description={t("moduleWorkbench.missingDesc")}
      >
        <BackButton />
      </EmptyState>
    );
  }

  const pages =
    pagesQuery.data?.filter((page) => page.moduleId === moduleId) ?? [];
  const pageItems: PageItem[] =
    pages.length > 0
      ? pages.map((page) => ({ id: page.id, title: page.title }))
      : readManifestPages(manifest);

  const apiTools = (
    (toolsQuery.data?.items ?? []) as unknown as ModuleToolContribution[]
  ).filter((tool) => tool.moduleId === moduleId);
  const tools = apiTools.length > 0 ? apiTools : readManifestTools(manifest, summary);
  const widgets = (widgetsQuery.data?.items ?? []).filter(
    (widget) => widget.moduleId === moduleId,
  );

  const models = readModels(manifest);
  const recordTypes = readRecordTypes(manifest);
  const resources = resourceLabels(t, manifest);
  const moduleType = manifest?.type ?? summary.type;
  const TypeIcon = moduleTypeIcon(moduleType);
  const isAnalysisModel = moduleType === "analysis-model";
  const running = summary.running || summary.state === "running";
  const toolsDisabled = !summary.enabled || summary.state === "crashed";
  const toolsDisabledReason = !summary.enabled
    ? t("moduleWorkbench.toolsDisabledHint")
    : summary.state === "crashed"
      ? t("moduleWorkbench.toolsCrashedHint")
      : undefined;

  const actionBusy = actionMutation.isPending
    ? (actionMutation.variables?.action ?? null)
    : null;
  const busyScope = grant.isPending
    ? (grant.variables ?? null)
    : revoke.isPending
      ? (revoke.variables ?? null)
      : null;
  const refreshing = modulesQuery.isFetching || manifestQuery.isFetching;

  return (
    <>
      <PageHeader
        eyebrow={t("moduleWorkbench.eyebrow")}
        title={displayName}
        description={manifest?.description ?? summary.description}
        actions={
          <>
            <BackButton />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={refreshAll}
              disabled={refreshing}
            >
              <RefreshCw
                className={cn(refreshing && "animate-spin")}
                aria-hidden="true"
              />
              {t("moduleWorkbench.refresh")}
            </Button>
            {summary.enabled ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={actionBusy !== null}
                onClick={() =>
                  actionMutation.mutate({ action: running ? "stop" : "start" })
                }
              >
                {actionBusy === "start" || actionBusy === "stop" ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : running ? (
                  <Square aria-hidden="true" />
                ) : (
                  <Play aria-hidden="true" />
                )}
                {running
                  ? t("moduleWorkbench.stop")
                  : t("moduleWorkbench.start")}
              </Button>
            ) : null}
            <Button
              type="button"
              variant={summary.enabled ? "outline" : "default"}
              size="sm"
              disabled={actionBusy !== null}
              onClick={() =>
                actionMutation.mutate({
                  action: summary.enabled ? "disable" : "enable",
                })
              }
            >
              {actionBusy === "enable" || actionBusy === "disable" ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : summary.enabled ? (
                <PowerOff aria-hidden="true" />
              ) : (
                <Power aria-hidden="true" />
              )}
              {summary.enabled
                ? t("moduleWorkbench.disable")
                : t("moduleWorkbench.enable")}
            </Button>
          </>
        }
      />

      <div className="space-y-4">
        {!summary.enabled ? (
          <Alert>
            <PowerOff aria-hidden="true" />
            <AlertTitle>{t("moduleWorkbench.disabledTitle")}</AlertTitle>
            <AlertDescription>{t("moduleWorkbench.disabledDesc")}</AlertDescription>
          </Alert>
        ) : null}

        {summary.state === "crashed" ? (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>{t("moduleWorkbench.crashedTitle")}</AlertTitle>
            <AlertDescription>{t("moduleWorkbench.crashedDesc")}</AlertDescription>
          </Alert>
        ) : null}

        {manifestQuery.isError ? (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>{t("moduleWorkbench.manifestLoadError")}</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{t("moduleWorkbench.manifestLoadErrorDesc")}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void manifestQuery.refetch()}
              >
                {t("common.retry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <TypeIcon className="size-4" aria-hidden="true" />
              {t("moduleWorkbench.overviewTitle")}
            </CardTitle>
            <CardDescription>
              {t("moduleWorkbench.overviewDesc")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <Fact label={t("moduleWorkbench.facts.version")}>
                v{manifest?.version ?? summary.version}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.type")}>
                {moduleTypeLabel(t, moduleType)}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.state")}>
                <ModuleStateBadge state={summary.state} />
              </Fact>
              <Fact label={t("moduleWorkbench.facts.installedAt")}>
                {formatDateTime(summary.installedAt, locale)}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.author")}>
                {manifest?.author?.name ?? "—"}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.license")}>
                {manifest?.license ?? "—"}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.resources")}>
                {resources.length > 0 ? (
                  <span className="flex flex-wrap gap-1">
                    {resources.map((label) => (
                      <Badge
                        key={label}
                        variant="outline"
                        className="font-normal"
                      >
                        {label}
                      </Badge>
                    ))}
                  </span>
                ) : (
                  <span className="text-muted-foreground">
                    {t("moduleUi.manifest.noResources")}
                  </span>
                )}
              </Fact>
              <Fact label={t("moduleWorkbench.facts.id")}>
                <code className="eh-caption break-all">{moduleId}</code>
              </Fact>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <LayoutGrid className="size-4" aria-hidden="true" />
              {t("moduleWorkbench.pagesTitle")}
            </CardTitle>
            <CardDescription>{t("moduleWorkbench.pagesDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {pagesQuery.isLoading ? (
              <div className="px-4 pb-4">
                <Skeleton className="h-16 w-full" />
              </div>
            ) : pageItems.length === 0 ? (
              <div className="px-4 pb-4">
                <p className="text-sm font-medium">
                  {t("moduleWorkbench.noPagesTitle")}
                </p>
                <p className="eh-caption mt-1 text-muted-foreground">
                  {t("moduleWorkbench.noPagesDesc")}
                </p>
                {pagesQuery.isError ? (
                  <p className="eh-caption mt-1 text-muted-foreground">
                    {moduleErrorMessage(pagesQuery.error, t)}
                  </p>
                ) : null}
              </div>
            ) : (
              <ul className="divide-y divide-border border-t border-border">
                {pageItems.map((page) => (
                  <li key={page.id}>
                    <Link
                      to={`/modules/${encodeURIComponent(moduleId)}/pages/${encodeURIComponent(page.id)}`}
                      className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-muted/50"
                    >
                      <span className="truncate font-medium">{page.title}</span>
                      <span className="eh-caption flex shrink-0 items-center gap-1 text-muted-foreground">
                        {t("moduleWorkbench.openPage")}
                        <ArrowUpRight className="size-3.5" aria-hidden="true" />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <BarChart3 className="size-4" aria-hidden="true" />
              {t("moduleWorkbench.widgetsTitle")}
            </CardTitle>
            <CardDescription>{t("moduleWorkbench.widgetsDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            {widgetsQuery.isLoading && widgets.length === 0 ? (
              <Skeleton className="h-24 w-full" />
            ) : widgets.length === 0 ? (
              <div>
                <p className="text-sm font-medium">
                  {t("moduleWorkbench.noWidgetsTitle")}
                </p>
                <p className="eh-caption mt-1 text-muted-foreground">
                  {t("moduleWorkbench.noWidgetsDesc")}
                </p>
                {widgetsQuery.isError ? (
                  <p className="eh-caption mt-1 text-muted-foreground">
                    {moduleErrorMessage(widgetsQuery.error, t)}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {widgets.map((widget) => (
                  <WidgetCard
                    key={`${widget.moduleId}:${widget.id}`}
                    widget={widget}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <Wrench className="size-4" aria-hidden="true" />
              {t("moduleWorkbench.toolsTitle")}
            </CardTitle>
            <CardDescription>{t("moduleWorkbench.toolsDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {toolsQuery.isLoading && tools.length === 0 ? (
              <div className="px-4 pb-4">
                <Skeleton className="h-16 w-full" />
              </div>
            ) : tools.length === 0 ? (
              <div className="px-4 pb-4">
                <p className="text-sm font-medium">
                  {t("moduleWorkbench.noToolsTitle")}
                </p>
                <p className="eh-caption mt-1 text-muted-foreground">
                  {t("moduleWorkbench.noToolsDesc")}
                </p>
                {toolsQuery.isError ? (
                  <p className="eh-caption mt-1 text-muted-foreground">
                    {moduleErrorMessage(toolsQuery.error, t)}
                  </p>
                ) : null}
              </div>
            ) : (
              <ul className="divide-y divide-border border-t border-border">
                {tools.map((tool) => (
                  <ToolRunner
                    key={tool.id}
                    moduleId={moduleId}
                    tool={tool}
                    disabled={toolsDisabled}
                    disabledReason={toolsDisabledReason}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="eh-h3 flex items-center gap-2">
                <TypeIcon className="size-4" aria-hidden="true" />
                {t("moduleWorkbench.modelsTitle")}
              </CardTitle>
              <CardDescription>{t("moduleWorkbench.modelsDesc")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {isAnalysisModel ? (
                <p className="eh-small flex flex-wrap items-center gap-2 text-muted-foreground">
                  {t("moduleWorkbench.modelUsageHint")}
                  <Link
                    to="/records"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    {t("moduleWorkbench.goToRecords")}
                    <ArrowUpRight className="size-3.5" aria-hidden="true" />
                  </Link>
                </p>
              ) : null}
              {models.length === 0 ? (
                <p className="eh-small text-muted-foreground">
                  {t("moduleWorkbench.noModels")}
                </p>
              ) : (
                <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                  {models.map((model) => (
                    <li key={model.id} className="space-y-1.5 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{model.name}</span>
                        <code className="eh-caption text-muted-foreground">
                          {model.id}
                        </code>
                        {model.nonDiagnostic ? (
                          <Badge
                            variant="outline"
                            className="font-normal text-muted-foreground"
                          >
                            {t("moduleWorkbench.nonDiagnostic")}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="eh-caption flex flex-wrap gap-x-4 text-muted-foreground">
                        {model.task ? (
                          <span>
                            {t("moduleWorkbench.modelTask")}: {model.task}
                          </span>
                        ) : null}
                        {model.format ? (
                          <span>
                            {t("moduleWorkbench.modelFormat")}: {model.format}
                          </span>
                        ) : null}
                      </div>
                      {model.limitations.length > 0 ? (
                        <p className="eh-caption text-muted-foreground">
                          <span className="font-medium">
                            {t("moduleWorkbench.modelLimitations")}:
                          </span>{" "}
                          {model.limitations.join(" · ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="eh-h3 flex items-center gap-2">
                <ListChecks className="size-4" aria-hidden="true" />
                {t("moduleWorkbench.recordTypesTitle")}
              </CardTitle>
              <CardDescription>
                {t("moduleWorkbench.recordTypesDesc")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {recordTypes.length === 0 ? (
                <p className="eh-small text-muted-foreground">
                  {t("moduleWorkbench.noRecordTypes")}
                </p>
              ) : (
                <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                  {recordTypes.map((recordType) => (
                    <li
                      key={recordType.id}
                      className="flex flex-wrap items-baseline gap-2 px-3 py-2 text-sm"
                    >
                      <span className="font-medium">{recordType.name}</span>
                      <code className="eh-caption text-muted-foreground">
                        {recordType.id}
                      </code>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="eh-h3 flex items-center gap-2">
                <ShieldCheck className="size-4" aria-hidden="true" />
                {t("moduleWorkbench.permissionsTitle")}
              </CardTitle>
              <CardDescription>
                {t("moduleWorkbench.permissionsDesc")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {!summary.enabled ? (
                <p className="eh-caption text-muted-foreground">
                  {t("moduleWorkbench.permissionsDisabledHint")}
                </p>
              ) : null}
              {permissionsQuery.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : null}
              {permissionsQuery.isError ? (
                <p className="eh-small text-muted-foreground">
                  {moduleErrorMessage(permissionsQuery.error, t)}
                </p>
              ) : null}
              {permissionsQuery.data ? (
                <PermissionManager
                  permissions={permissionsQuery.data.scopes}
                  busyScope={busyScope}
                  onGrant={(scope) => grant.mutate(scope)}
                  onRevoke={(scope) => revoke.mutate(scope)}
                />
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="eh-h3 flex items-center gap-2">
                <History className="size-4" aria-hidden="true" />
                {t("moduleWorkbench.auditTitle")}
              </CardTitle>
              <CardDescription>{t("moduleWorkbench.auditDesc")}</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {auditQuery.isLoading ? (
                <div className="px-4 pb-4">
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : null}
              {auditQuery.isError ? (
                <p className="eh-small px-4 pb-4 text-muted-foreground">
                  {t("moduleWorkbench.auditLoadError")}
                  {": "}
                  {moduleErrorMessage(auditQuery.error, t)}
                </p>
              ) : null}
              {auditQuery.data ? (
                auditQuery.data.events.length === 0 ? (
                  <p className="eh-small px-4 pb-4 text-muted-foreground">
                    {t("moduleWorkbench.noAudit")}
                  </p>
                ) : (
                  <ul className="divide-y divide-border border-t border-border">
                    {auditQuery.data.events.map((event) => (
                      <AuditEventRow key={event.id} event={event} />
                    ))}
                  </ul>
                )
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

import "./i18n";
import "../i18n";

import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import type { LucideIcon } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  BadgeCheck,
  Boxes,
  CalendarClock,
  Cpu,
  History,
  LayoutGrid,
  ListChecks,
  Loader2,
  Play,
  Power,
  PowerOff,
  RefreshCw,
  Scale,
  ShieldCheck,
  Square,
  User,
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
import {
  getModuleCopy,
  isFirstPartyModule,
  moduleDisplayName,
  moduleSummary,
} from "../copy";
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

function MetaItem({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <Icon
        className="size-3.5 shrink-0 text-muted-foreground/70"
        aria-hidden="true"
      />
      <span className="shrink-0">{label}</span>
      <span className="min-w-0 truncate font-medium text-foreground">
        {children}
      </span>
    </span>
  );
}

function StatusLine({
  icon: Icon,
  title,
  hint,
  error,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  error?: string;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-dashed border-border px-3 py-2 text-muted-foreground eh-small">
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <span className="font-medium text-foreground/80">{title}</span>
      {hint ? <span className="eh-caption">{hint}</span> : null}
      {error ? (
        <span className="eh-caption text-destructive">{error}</span>
      ) : null}
    </div>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
}) {
  return (
    <div className="space-y-0.5">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
        {title}
      </h2>
      {description ? (
        <p className="eh-caption pl-6 text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function SectionCard({
  icon: Icon,
  title,
  description,
  children,
  contentClassName,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  children: ReactNode;
  contentClassName?: string;
}) {
  return (
    <Card size="sm" className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
          {title}
        </CardTitle>
        {description ? (
          <CardDescription className="eh-caption">
            {description}
          </CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className={contentClassName}>{children}</CardContent>
    </Card>
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
    <div className="space-y-4" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <Skeleton className="h-10 w-full rounded-lg" />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
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
  const description = moduleSummary(
    i18n.language,
    moduleId,
    manifest?.description ?? summary?.description ?? "",
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
  const tools =
    apiTools.length > 0 ? apiTools : readManifestTools(manifest, summary);
  const widgets = (widgetsQuery.data?.items ?? []).filter(
    (widget) => widget.moduleId === moduleId,
  );

  const models = readModels(manifest);
  const moduleCopy = getModuleCopy(i18n.language, moduleId);
  const recordTypes = readRecordTypes(manifest);
  const resources = resourceLabels(t, manifest);
  const moduleType = manifest?.type ?? summary.type;
  const moduleVersion = manifest?.version ?? summary.version;
  const TypeIcon = moduleTypeIcon(moduleType);
  const isAnalysisModel = moduleType === "analysis-model";
  const running = summary.running || summary.state === "running";
  const firstParty = isFirstPartyModule(moduleId);
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
      <header className="mb-6">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <p className="eh-caption tracking-[0.14em] text-muted-foreground uppercase">
              {t("moduleWorkbench.eyebrow")}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h1 className="eh-h1">{displayName}</h1>
              <Badge variant="secondary" className="font-normal">
                v{moduleVersion}
              </Badge>
              <Badge
                variant="outline"
                className="font-normal text-muted-foreground"
              >
                {moduleTypeLabel(t, moduleType)}
              </Badge>
              <ModuleStateBadge state={summary.state} />
              {firstParty ? (
                <Badge variant="secondary" className="gap-1 font-normal">
                  <BadgeCheck className="size-3" aria-hidden="true" />
                  {t("moduleUi.marketplace.firstParty")}
                </Badge>
              ) : null}
            </div>
            {description ? (
              <p className="eh-small mt-2 max-w-[72ch] text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <BackButton />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("moduleWorkbench.refresh")}
              onClick={refreshAll}
              disabled={refreshing}
            >
              <RefreshCw
                className={cn(refreshing && "animate-spin")}
                aria-hidden="true"
              />
            </Button>
            <span
              className="mx-0.5 hidden h-5 w-px bg-border sm:block"
              aria-hidden="true"
            />
            {summary.enabled ? (
              <Button
                type="button"
                variant={running ? "outline" : "default"}
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
          </div>
        </div>

        <div className="mt-3 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-border bg-card px-3 py-2 text-muted-foreground eh-caption">
          <MetaItem icon={User} label={t("moduleWorkbench.facts.author")}>
            {manifest?.author?.name ?? "—"}
          </MetaItem>
          <MetaItem icon={Scale} label={t("moduleWorkbench.facts.license")}>
            {manifest?.license ?? "—"}
          </MetaItem>
          <MetaItem
            icon={CalendarClock}
            label={t("moduleWorkbench.facts.installedAt")}
          >
            {formatDateTime(summary.installedAt, locale)}
          </MetaItem>
          <span className="inline-flex min-w-0 flex-wrap items-center gap-1.5">
            <Cpu
              className="size-3.5 shrink-0 text-muted-foreground/70"
              aria-hidden="true"
            />
            <span className="shrink-0">
              {t("moduleWorkbench.facts.resources")}
            </span>
            {resources.length > 0 ? (
              resources.map((label) => (
                <Badge
                  key={label}
                  variant="outline"
                  className="font-normal text-muted-foreground"
                >
                  {label}
                </Badge>
              ))
            ) : (
              <span className="font-medium text-foreground">
                {t("moduleUi.manifest.noResources")}
              </span>
            )}
          </span>
          <code className="min-w-0 truncate opacity-80" title={moduleId}>
            {moduleId}
          </code>
        </div>
      </header>

      {!summary.enabled ||
      summary.state === "crashed" ||
      manifestQuery.isError ? (
        <div className="mb-4 space-y-3">
          {!summary.enabled ? (
            <Alert>
              <PowerOff aria-hidden="true" />
              <AlertTitle>{t("moduleWorkbench.disabledTitle")}</AlertTitle>
              <AlertDescription>
                {t("moduleWorkbench.disabledDesc")}
              </AlertDescription>
            </Alert>
          ) : null}

          {summary.state === "crashed" ? (
            <Alert variant="destructive">
              <AlertCircle aria-hidden="true" />
              <AlertTitle>{t("moduleWorkbench.crashedTitle")}</AlertTitle>
              <AlertDescription>
                {t("moduleWorkbench.crashedDesc")}
              </AlertDescription>
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
        </div>
      ) : null}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          {pagesQuery.isLoading && pageItems.length === 0 ? (
            <Skeleton className="h-14 w-full rounded-lg" />
          ) : pageItems.length === 0 ? (
            <StatusLine
              icon={LayoutGrid}
              title={t("moduleWorkbench.noPagesTitle")}
              hint={t("moduleWorkbench.noPagesDesc")}
              error={
                pagesQuery.isError
                  ? moduleErrorMessage(pagesQuery.error, t)
                  : undefined
              }
            />
          ) : (
            <SectionCard
              icon={LayoutGrid}
              title={t("moduleWorkbench.pagesTitle")}
              description={t("moduleWorkbench.pagesDesc")}
              contentClassName="p-0"
            >
              <ul className="divide-y divide-border">
                {pageItems.map((page) => (
                  <li key={page.id}>
                    <Link
                      to={`/modules/${encodeURIComponent(moduleId)}/pages/${encodeURIComponent(page.id)}`}
                      className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm transition-colors hover:bg-muted/50"
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
            </SectionCard>
          )}

          {widgetsQuery.isLoading && widgets.length === 0 ? (
            <Skeleton className="h-16 w-full rounded-lg" />
          ) : widgets.length === 0 ? (
            <StatusLine
              icon={BarChart3}
              title={t("moduleWorkbench.noWidgetsTitle")}
              hint={t("moduleWorkbench.noWidgetsDesc")}
              error={
                widgetsQuery.isError
                  ? moduleErrorMessage(widgetsQuery.error, t)
                  : undefined
              }
            />
          ) : (
            <section className="min-w-0 space-y-2">
              <SectionHeading
                icon={BarChart3}
                title={t("moduleWorkbench.widgetsTitle")}
                description={t("moduleWorkbench.widgetsDesc")}
              />
              <div className="grid gap-3 lg:grid-cols-2">
                {widgets.map((widget) => (
                  <WidgetCard
                    key={`${widget.moduleId}:${widget.id}`}
                    widget={widget}
                  />
                ))}
              </div>
            </section>
          )}

          {toolsQuery.isLoading && tools.length === 0 ? (
            <Skeleton className="h-14 w-full rounded-lg" />
          ) : tools.length === 0 ? (
            <StatusLine
              icon={Wrench}
              title={t("moduleWorkbench.noToolsTitle")}
              hint={
                !summary.enabled
                  ? t("moduleWorkbench.toolsDisabledHint")
                  : t("moduleWorkbench.noToolsDesc")
              }
              error={
                toolsQuery.isError
                  ? moduleErrorMessage(toolsQuery.error, t)
                  : undefined
              }
            />
          ) : (
            <SectionCard
              icon={Wrench}
              title={t("moduleWorkbench.toolsTitle")}
              description={t("moduleWorkbench.toolsDesc")}
              contentClassName="p-0"
            >
              <ul className="divide-y divide-border">
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
            </SectionCard>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {models.length > 0 ? (
              <SectionCard
                icon={TypeIcon}
                title={t("moduleWorkbench.modelsTitle")}
                description={t("moduleWorkbench.modelsDesc")}
              >
                <div className="space-y-3">
                  {isAnalysisModel ? (
                    <p className="eh-small flex flex-wrap items-center gap-2 text-muted-foreground">
                      {t("moduleWorkbench.modelUsageHint")}
                      <Link
                        to="/records"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        {t("moduleWorkbench.goToRecords")}
                        <ArrowUpRight
                          className="size-3.5"
                          aria-hidden="true"
                        />
                      </Link>
                    </p>
                  ) : null}
                  <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                    {models.map((model) => {
                      // 模块文案（中/英）优先于 manifest 里常见的技术英文限制。
                      const limits = moduleCopy?.limits?.length
                        ? moduleCopy.limits
                        : model.limitations;
                      return (
                      <li key={model.id} className="space-y-1.5 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">
                            {model.name}
                          </span>
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
                              {t("moduleWorkbench.modelFormat")}:{" "}
                              {model.format}
                            </span>
                          ) : null}
                        </div>
                        {limits.length > 0 ? (
                          <p className="eh-caption text-muted-foreground">
                            <span className="font-medium">
                              {t("moduleWorkbench.modelLimitations")}:
                            </span>{" "}
                            {limits.join(" · ")}
                          </p>
                        ) : null}
                      </li>
                      );
                    })}
                  </ul>
                </div>
              </SectionCard>
            ) : (
              <StatusLine
                icon={TypeIcon}
                title={t("moduleWorkbench.noModels")}
              />
            )}

            {recordTypes.length > 0 ? (
              <SectionCard
                icon={ListChecks}
                title={t("moduleWorkbench.recordTypesTitle")}
                description={t("moduleWorkbench.recordTypesDesc")}
              >
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
              </SectionCard>
            ) : (
              <StatusLine
                icon={ListChecks}
                title={t("moduleWorkbench.noRecordTypes")}
              />
            )}
          </div>
        </div>

        <div className="min-w-0 space-y-4">
          <SectionCard
            icon={ShieldCheck}
            title={t("moduleWorkbench.permissionsTitle")}
            description={t("moduleWorkbench.permissionsDesc")}
          >
            <div className="space-y-2">
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
            </div>
          </SectionCard>

          <SectionCard
            icon={History}
            title={t("moduleWorkbench.auditTitle")}
            description={t("moduleWorkbench.auditDesc")}
            contentClassName="p-0"
          >
            {auditQuery.isLoading ? (
              <div className="px-3 pb-3">
                <Skeleton className="h-20 w-full" />
              </div>
            ) : null}
            {auditQuery.isError ? (
              <p className="eh-small px-3 pb-3 text-muted-foreground">
                {t("moduleWorkbench.auditLoadError")}
                {": "}
                {moduleErrorMessage(auditQuery.error, t)}
              </p>
            ) : null}
            {auditQuery.data ? (
              auditQuery.data.events.length === 0 ? (
                <div className="px-3 pb-3">
                  <p className="eh-caption rounded-lg border border-dashed border-border px-3 py-2 text-muted-foreground">
                    {t("moduleWorkbench.noAudit")}
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {auditQuery.data.events.map((event) => (
                    <AuditEventRow key={event.id} event={event} />
                  ))}
                </ul>
              )
            ) : null}
          </SectionCard>
        </div>
      </div>
    </>
  );
}

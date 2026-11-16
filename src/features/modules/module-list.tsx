import { useMemo, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  BadgeCheck,
  Blocks,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  Play,
  Power,
  PowerOff,
  RefreshCw,
  Search,
  Settings2,
  Square,
  Trash2,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/common/empty-state";
import { RecordListSkeleton } from "@/components/common/loading";
import { intlLocale } from "@/lib/i18n";
import {
  getModuleCopy,
  isFirstPartyModule,
  moduleDisplayName,
  moduleMatchesQuery,
  moduleTagline,
} from "./copy";
import { formatDateTime, moduleTypeLabel } from "./format";
import { ModuleTypeIcon } from "./module-icon";
import { ModuleStateBadge } from "./state-badge";
import type { ModuleSummary } from "./types";

export type ModuleAction = "start" | "stop" | "enable" | "disable";

interface ModuleListProps {
  modules: ModuleSummary[];
  loading: boolean;
  busy: { moduleId: string; action: string } | null;
  onAction: (module: ModuleSummary, action: ModuleAction) => void;
  onOpen: (module: ModuleSummary) => void;
  onDetails: (module: ModuleSummary) => void;
  onUninstall: (module: ModuleSummary) => void;
  onRefresh: () => void;
}

function permissionCount(t: TFunction, module: ModuleSummary): string {
  return t("moduleUi.permissionCount", {
    count: module.grantedPermissions.length,
  });
}

export function ModuleList({
  modules,
  loading,
  busy,
  onAction,
  onOpen,
  onDetails,
  onUninstall,
  onRefresh,
}: ModuleListProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [search, setSearch] = useState("");
  const running = modules.filter((module) => module.running).length;

  const visibleModules = useMemo(
    () =>
      modules.filter((module) =>
        moduleMatchesQuery(
          module,
          getModuleCopy(i18n.language, module.id),
          search,
        ),
      ),
    [modules, search, i18n.language],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="eh-h3">{t("moduleUi.installedTitle")}</CardTitle>
        <CardDescription>{t("moduleUi.installedDesc")}</CardDescription>
        <CardAction className="flex items-center gap-2">
          {modules.length > 0 ? (
            <span className="eh-caption text-muted-foreground">
              {t("moduleUi.counts", { total: modules.length, running })}
            </span>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={t("moduleUi.refresh")}
            disabled={loading}
            onClick={onRefresh}
          >
            {loading ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw aria-hidden="true" />
            )}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="p-0">
        {loading && modules.length === 0 ? (
          <RecordListSkeleton rows={3} />
        ) : modules.length === 0 ? (
          <EmptyState
            icon={Blocks}
            title={t("moduleUi.emptyTitle")}
            description={t("moduleUi.emptyDesc")}
            className="m-4"
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2.5">
              <div className="relative min-w-[12rem] flex-1">
                <Search
                  className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("moduleUi.list.searchPlaceholder")}
                  aria-label={t("moduleUi.list.searchPlaceholder")}
                  className="pl-8"
                />
              </div>
              <span className="eh-caption tabular-nums text-muted-foreground">
                {t("moduleUi.list.resultCount", {
                  shown: visibleModules.length,
                  total: modules.length,
                })}
              </span>
            </div>

            {visibleModules.length === 0 ? (
              <EmptyState
                icon={Search}
                title={t("moduleUi.list.searchEmptyTitle")}
                description={t("moduleUi.list.searchEmptyDesc")}
                className="m-4"
              >
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSearch("")}
                >
                  {t("moduleUi.list.clearSearch")}
                </Button>
              </EmptyState>
            ) : (
              <ul className="eh-stagger divide-y divide-border border-t border-border">
                {visibleModules.map((module) => {
                  const actionBusy =
                    busy?.moduleId === module.id ? busy.action : null;
                  const name = moduleDisplayName(
                    i18n.language,
                    module.id,
                    module.name,
                  );
                  const tagline = moduleTagline(
                    i18n.language,
                    module.id,
                    module.description,
                  );
                  const firstParty = isFirstPartyModule(module.id);
                  const isRunning =
                    module.running || module.state === "running";

                  return (
                    <li
                      key={module.id}
                      className="group flex flex-col gap-3 px-4 py-3.5 transition-colors hover:bg-muted/40 focus-within:bg-muted/30 md:flex-row md:items-center"
                    >
                      <span
                        className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-primary"
                        aria-hidden="true"
                      >
                        <ModuleTypeIcon
                          type={module.type}
                          className="size-4"
                        />
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <button
                            type="button"
                            className="min-w-0 max-w-full truncate text-sm font-medium hover:underline"
                            title={name}
                            onClick={() => onDetails(module)}
                          >
                            {name}
                          </button>
                          <Badge variant="secondary" className="font-normal">
                            v{module.version}
                          </Badge>
                          {firstParty ? (
                            <Badge
                              variant="secondary"
                              className="gap-1 font-normal"
                            >
                              <BadgeCheck className="size-3" aria-hidden="true" />
                              {t("moduleUi.marketplace.firstParty")}
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="gap-1 font-normal text-muted-foreground"
                            >
                              <Users className="size-3" aria-hidden="true" />
                              {t("moduleUi.list.community")}
                            </Badge>
                          )}
                          <ModuleStateBadge state={module.state} />
                          <Badge
                            variant="outline"
                            className="font-normal text-muted-foreground"
                          >
                            {moduleTypeLabel(t, module.type)}
                          </Badge>
                        </div>
                        {tagline ? (
                          <p className="eh-caption mt-1 line-clamp-1 text-muted-foreground">
                            {tagline}
                          </p>
                        ) : null}
                        <p className="eh-caption mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-muted-foreground">
                          <span>{permissionCount(t, module)}</span>
                          <span aria-hidden="true">·</span>
                          <span>
                            {t("moduleUi.installedAt", {
                              date: formatDateTime(
                                module.installedAt,
                                locale,
                              ),
                            })}
                          </span>
                          <span aria-hidden="true">·</span>
                          <code
                            className="min-w-0 max-w-full truncate"
                            title={module.id}
                          >
                            {module.id}
                          </code>
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-1.5 md:justify-end">
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => onOpen(module)}
                        >
                          <ExternalLink aria-hidden="true" />
                          {t("moduleUi.actions.open")}
                        </Button>

                        {module.enabled ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={actionBusy !== null}
                            onClick={() =>
                              onAction(module, isRunning ? "stop" : "start")
                            }
                          >
                            {actionBusy === "start" ||
                            actionBusy === "stop" ? (
                              <Loader2
                                className="animate-spin"
                                aria-hidden="true"
                              />
                            ) : isRunning ? (
                              <Square aria-hidden="true" />
                            ) : (
                              <Play aria-hidden="true" />
                            )}
                            {isRunning
                              ? t("moduleUi.actions.stop")
                              : t("moduleUi.actions.start")}
                          </Button>
                        ) : null}

                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              aria-label={t("moduleUi.actions.more")}
                              disabled={actionBusy !== null}
                            >
                              <MoreHorizontal aria-hidden="true" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="min-w-40">
                            <DropdownMenuItem
                              onSelect={() => onDetails(module)}
                            >
                              <Settings2 aria-hidden="true" />
                              {t("moduleUi.actions.details")}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onSelect={() =>
                                onAction(
                                  module,
                                  module.enabled ? "disable" : "enable",
                                )
                              }
                            >
                              {module.enabled ? (
                                <PowerOff aria-hidden="true" />
                              ) : (
                                <Power aria-hidden="true" />
                              )}
                              {module.enabled
                                ? t("moduleUi.actions.disable")
                                : t("moduleUi.actions.enable")}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => onUninstall(module)}
                            >
                              <Trash2 aria-hidden="true" />
                              {t("moduleUi.actions.uninstall")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

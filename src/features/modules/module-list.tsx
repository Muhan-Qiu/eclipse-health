import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  Blocks,
  Loader2,
  Power,
  PowerOff,
  RefreshCw,
  Settings2,
  Square,
  Trash2,
  Play,
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
import { EmptyState } from "@/components/common/empty-state";
import { RecordListSkeleton } from "@/components/common/loading";
import { intlLocale } from "@/lib/i18n";
import { formatDateTime, moduleTypeLabel } from "./format";
import { ModuleStateBadge } from "./state-badge";
import type { ModuleSummary } from "./types";

export type ModuleAction = "start" | "stop" | "enable" | "disable";

interface ModuleListProps {
  modules: ModuleSummary[];
  loading: boolean;
  busy: { moduleId: string; action: string } | null;
  onAction: (module: ModuleSummary, action: ModuleAction) => void;
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
  onDetails,
  onUninstall,
  onRefresh,
}: ModuleListProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const running = modules.filter((module) => module.running).length;

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
            <RefreshCw aria-hidden="true" />
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
          <ul className="divide-y divide-border border-t border-border">
            {modules.map((module) => {
              const actionBusy =
                busy?.moduleId === module.id ? busy.action : null;
              return (
                <li
                  key={module.id}
                  className="flex flex-col gap-3 px-4 py-3.5 md:flex-row md:items-center"
                >
                  <span
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-primary"
                    aria-hidden="true"
                  >
                    <Blocks className="size-4" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="truncate text-sm font-medium hover:underline"
                        onClick={() => onDetails(module)}
                      >
                        {module.name}
                      </button>
                      <Badge variant="secondary" className="font-normal">
                        v{module.version}
                      </Badge>
                      <ModuleStateBadge state={module.state} />
                      <Badge
                        variant="outline"
                        className="font-normal text-muted-foreground"
                      >
                        {moduleTypeLabel(t, module.type)}
                      </Badge>
                    </div>
                    <p className="eh-caption mt-0.5 truncate text-muted-foreground">
                      {module.id}
                      {" · "}
                      {permissionCount(t, module)}
                      {" · "}
                      {t("moduleUi.installedAt", {
                        date: formatDateTime(module.installedAt, locale),
                      })}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 md:justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => onDetails(module)}
                    >
                      <Settings2 aria-hidden="true" />
                      {t("moduleUi.actions.details")}
                    </Button>

                    {module.enabled ? (
                      module.running || module.state === "running" ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={actionBusy !== null}
                          onClick={() => onAction(module, "stop")}
                        >
                          {actionBusy === "stop" ? (
                            <Loader2 className="animate-spin" aria-hidden="true" />
                          ) : (
                            <Square aria-hidden="true" />
                          )}
                          {t("moduleUi.actions.stop")}
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={actionBusy !== null}
                          onClick={() => onAction(module, "start")}
                        >
                          {actionBusy === "start" ? (
                            <Loader2 className="animate-spin" aria-hidden="true" />
                          ) : (
                            <Play aria-hidden="true" />
                          )}
                          {t("moduleUi.actions.start")}
                        </Button>
                      )
                    ) : null}

                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={actionBusy !== null}
                      onClick={() =>
                        onAction(module, module.enabled ? "disable" : "enable")
                      }
                    >
                      {actionBusy === "enable" || actionBusy === "disable" ? (
                        <Loader2 className="animate-spin" aria-hidden="true" />
                      ) : module.enabled ? (
                        <PowerOff aria-hidden="true" />
                      ) : (
                        <Power aria-hidden="true" />
                      )}
                      {module.enabled
                        ? t("moduleUi.actions.disable")
                        : t("moduleUi.actions.enable")}
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground hover:text-destructive"
                      disabled={actionBusy !== null}
                      onClick={() => onUninstall(module)}
                    >
                      <Trash2 aria-hidden="true" />
                      {t("moduleUi.actions.uninstall")}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

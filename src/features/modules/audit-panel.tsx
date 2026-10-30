import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, ScrollText } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { listAudit } from "./api";
import { AuditEventRow } from "./audit-row";
import { moduleErrorMessage } from "./errors";
import { actionKey } from "./permission-utils";
import type { ModuleSummary } from "./types";

const ALL = "__all__";

const AUDIT_ACTIONS = [
  "module.install",
  "module.update",
  "module.uninstall",
  "module.enable",
  "module.disable",
  "module.start",
  "module.stop",
  "module.crash",
  "module.rollback",
  "permission.grant",
  "permission.revoke",
  "rpc.call",
  "core.call",
  "module.event",
] as const;

interface AuditPanelProps {
  modules: ModuleSummary[];
  moduleId: string;
  action: string;
  onModuleChange: (moduleId: string) => void;
  onActionChange: (action: string) => void;
  refreshToken: number;
}

export function AuditPanel({
  modules,
  moduleId,
  action,
  onModuleChange,
  onActionChange,
  refreshToken,
}: AuditPanelProps) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState(20);

  useEffect(() => {
    setLimit(20);
  }, [moduleId, action, refreshToken]);

  const auditQuery = useQuery({
    queryKey: ["modules", "audit", moduleId, action, limit, refreshToken],
    queryFn: () =>
      listAudit({
        moduleId: moduleId || undefined,
        action: action || undefined,
        limit,
      }),
  });

  const events = auditQuery.data?.events ?? [];
  const hasMore = auditQuery.data?.hasMore === true;

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="eh-h3 flex items-center gap-2">
          <ScrollText className="size-4 text-muted-foreground" aria-hidden="true" />
          {t("moduleUi.audit.title")}
        </CardTitle>
        <CardDescription>{t("moduleUi.audit.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Select
            value={moduleId || ALL}
            onValueChange={(value) => onModuleChange(value === ALL ? "" : value)}
          >
            <SelectTrigger size="sm" aria-label={t("moduleUi.audit.module")}>
              <SelectValue placeholder={t("moduleUi.audit.allModules")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t("moduleUi.audit.allModules")}</SelectItem>
              {modules.map((module) => (
                <SelectItem key={module.id} value={module.id}>
                  {module.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={action || ALL}
            onValueChange={(value) => onActionChange(value === ALL ? "" : value)}
          >
            <SelectTrigger size="sm" aria-label={t("moduleUi.audit.action")}>
              <SelectValue placeholder={t("moduleUi.audit.allActions")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t("moduleUi.audit.allActions")}</SelectItem>
              {AUDIT_ACTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`moduleUi.audit.actions.${actionKey(value)}`, {
                    defaultValue: value,
                  })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {auditQuery.isError ? (
          <Alert variant="destructive">
            <AlertTitle>{t("moduleUi.audit.loadError")}</AlertTitle>
            <AlertDescription>
              {moduleErrorMessage(auditQuery.error, t)}
            </AlertDescription>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void auditQuery.refetch()}
            >
              {t("common.retry")}
            </Button>
          </Alert>
        ) : null}

        {auditQuery.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : null}

        {!auditQuery.isLoading && !auditQuery.isError && events.length === 0 ? (
          <p className="eh-small rounded-lg border border-dashed border-border px-4 py-6 text-center text-muted-foreground">
            {t("moduleUi.audit.empty")}
          </p>
        ) : null}

        {events.length > 0 ? (
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {events.map((event) => (
              <AuditEventRow
                key={event.id}
                event={event}
                showModule={!moduleId}
              />
            ))}
          </ul>
        ) : null}

        {hasMore ? (
          <div className="flex justify-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={auditQuery.isFetching}
              onClick={() => setLimit((value) => value + 20)}
            >
              {auditQuery.isFetching ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : null}
              {t("moduleUi.audit.loadMore")}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

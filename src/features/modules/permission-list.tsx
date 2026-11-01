import { useTranslation } from "react-i18next";
import { Check, Minus } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  permissionDescription,
  permissionLabel,
  riskLabel,
  riskVariant,
  scopeKey,
} from "./permission-utils";
import type { PermissionDetail } from "./types";

interface PermissionChecklistProps {
  permissions: PermissionDetail[];
  selected: Set<string>;
  newScopes?: string[];
  onToggle: (scope: string) => void;
}

export function PermissionChecklist({
  permissions,
  selected,
  newScopes = [],
  onToggle,
}: PermissionChecklistProps) {
  const { t } = useTranslation();

  if (permissions.length === 0) {
    return (
      <p className="eh-small rounded-lg border border-dashed border-border p-3 text-muted-foreground">
        {t("moduleUi.installFlow.noPermissions")}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
      {permissions.map((item) => {
        const inputId = `module-permission-${scopeKey(item.scope)}`;
        const descriptionId = `${inputId}-desc`;
        const isNew = newScopes.includes(item.scope);
        return (
          <li
            key={item.scope}
            className={cn(
              "flex gap-3 p-3",
              item.risk === "high" && "bg-destructive/5",
            )}
          >
            <input
              id={inputId}
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-primary"
              checked={selected.has(item.scope)}
              aria-describedby={descriptionId}
              onChange={() => onToggle(item.scope)}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor={inputId} className="text-sm font-medium">
                  {permissionLabel(t, item)}
                </label>
                <Badge variant={riskVariant(item.risk)} className="font-normal">
                  {riskLabel(t, item.risk)}
                </Badge>
                {isNew ? (
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    {t("moduleUi.installFlow.newBadge")}
                  </Badge>
                ) : null}
                <code className="eh-caption text-muted-foreground">{item.scope}</code>
              </div>
              <p id={descriptionId} className="eh-caption mt-1 text-muted-foreground">
                {permissionDescription(t, item)}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

interface PermissionManagerProps {
  permissions: PermissionDetail[];
  busyScope: string | null;
  onGrant: (scope: string) => void;
  onRevoke: (scope: string) => void;
}

export function PermissionManager({
  permissions,
  busyScope,
  onGrant,
  onRevoke,
}: PermissionManagerProps) {
  const { t } = useTranslation();

  if (permissions.length === 0) {
    return (
      <p className="eh-small text-muted-foreground">
        {t("moduleUi.installFlow.noPermissions")}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
      {permissions.map((item) => {
        const granted = item.granted === true;
        const busy = busyScope === item.scope;
        return (
          <li key={item.scope} className="flex items-start gap-3 p-3">
            <span
              className={cn(
                "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full",
                granted
                  ? "bg-primary/10 text-primary"
                  : "bg-subtle text-muted-foreground",
              )}
              aria-hidden="true"
            >
              {granted ? <Check className="size-3" /> : <Minus className="size-3" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{permissionLabel(t, item)}</span>
                <Badge variant={riskVariant(item.risk)} className="font-normal">
                  {riskLabel(t, item.risk)}
                </Badge>
                <Badge variant="outline" className="font-normal text-muted-foreground">
                  {granted
                    ? t("moduleUi.permissions.granted")
                    : t("moduleUi.permissions.notGranted")}
                </Badge>
              </div>
              <p className="eh-caption mt-1 text-muted-foreground">
                {permissionDescription(t, item)}
              </p>
            </div>
            <Button
              type="button"
              variant={granted ? "destructive" : "outline"}
              size="sm"
              disabled={busy}
              onClick={() => (granted ? onRevoke(item.scope) : onGrant(item.scope))}
            >
              {granted ? t("moduleUi.permissions.revoke") : t("moduleUi.permissions.grant")}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { intlLocale } from "@/lib/i18n";
import { actionKey } from "./permission-utils";
import { formatDateTime } from "./format";
import type { AuditEvent } from "./types";

export function auditActionLabel(t: TFunction, action: string): string {
  return t(`moduleUi.audit.actions.${actionKey(action)}`, {
    defaultValue: action,
  });
}

interface AuditEventRowProps {
  event: AuditEvent;
  showModule?: boolean;
}

export function AuditEventRow({ event, showModule = false }: AuditEventRowProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
      <time
        className="eh-caption tabular-nums text-muted-foreground"
        dateTime={event.createdAt}
      >
        {formatDateTime(event.createdAt, locale)}
      </time>
      <span className="font-medium">{auditActionLabel(t, event.action)}</span>
      {event.scope ? (
        <code className="eh-caption rounded bg-subtle px-1.5 py-0.5 text-muted-foreground">
          {event.scope}
        </code>
      ) : null}
      {showModule && event.moduleId ? (
        <code className="eh-caption text-muted-foreground">{event.moduleId}</code>
      ) : null}
    </li>
  );
}

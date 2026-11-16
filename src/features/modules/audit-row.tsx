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
  /** 全局审计列表中用于替代原始 moduleId 的本地化名称。 */
  moduleName?: string;
}

export function AuditEventRow({
  event,
  showModule = false,
  moduleName,
}: AuditEventRowProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  return (
    <li className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2.5 text-sm">
      <time
        className="eh-caption shrink-0 tabular-nums text-muted-foreground"
        dateTime={event.createdAt}
      >
        {formatDateTime(event.createdAt, locale)}
      </time>
      <span className="font-medium">{auditActionLabel(t, event.action)}</span>
      {event.scope ? (
        <code className="eh-caption max-w-full truncate rounded bg-subtle px-1.5 py-0.5 text-muted-foreground">
          {event.scope}
        </code>
      ) : null}
      {showModule && event.moduleId ? (
        <span
          className="eh-caption min-w-0 max-w-[16rem] truncate text-muted-foreground"
          title={event.moduleId}
        >
          {moduleName ?? event.moduleId}
        </span>
      ) : null}
    </li>
  );
}

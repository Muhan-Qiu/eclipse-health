import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "cn";
import { intlLocale } from "@/lib/i18n";
import type { AssistantSession } from "./types";

export interface SessionListProps {
  sessions: AssistantSession[];
  activeId: string | null;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

export function SessionList({
  sessions,
  activeId,
  onCreate,
  onSelect,
  onDelete,
}: SessionListProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="eh-h3">{t("assistant.sessions.title")}</CardTitle>
        <CardDescription>{t("assistant.sessions.description")}</CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={onCreate}>
            <Plus data-icon="inline-start" />
            {t("assistant.sessions.new")}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/40 p-4 text-center">
            <p className="eh-small font-medium">{t("assistant.sessions.empty")}</p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("assistant.sessions.emptyDesc")}
            </p>
          </div>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => {
              const active = session.id === activeId;
              return (
                <li key={session.id} className="group/session relative">
                  <button
                    type="button"
                    onClick={() => onSelect(session.id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full items-start gap-2.5 rounded-lg border px-2.5 py-2 pr-9 text-left transition-colors",
                      active
                        ? "border-primary/40 bg-accent-soft"
                        : "border-transparent hover:bg-muted/60",
                    )}
                  >
                    <MessageSquare
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {session.title || t("assistant.sessionFallback")}
                      </span>
                      <span className="eh-caption block truncate text-muted-foreground">
                        {t("assistant.sessions.messageCount", {
                          count: session.messageCount,
                        })}
                        {" · "}
                        {new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
                          new Date(session.updatedAt),
                        )}
                      </span>
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant={confirming === session.id ? "destructive" : "ghost"}
                    size="icon-xs"
                    className="absolute top-1.5 right-1.5 opacity-0 group-hover/session:opacity-100 focus-visible:opacity-100"
                    aria-label={
                      confirming === session.id
                        ? t("assistant.sessions.deleteConfirm")
                        : t("assistant.sessions.delete")
                    }
                    title={
                      confirming === session.id
                        ? t("assistant.sessions.deleteConfirm")
                        : t("assistant.sessions.delete")
                    }
                    onClick={() => {
                      if (confirming === session.id) {
                        setConfirming(null);
                        onDelete(session.id);
                      } else {
                        setConfirming(session.id);
                      }
                    }}
                    onBlur={() => setConfirming(null)}
                  >
                    <Trash2 />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

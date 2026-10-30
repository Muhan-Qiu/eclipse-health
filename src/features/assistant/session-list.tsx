import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Download,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "cn";
import { intlLocale } from "@/lib/i18n";
import type { AssistantSession } from "./types";

const SEARCH_DEBOUNCE_MS = 300;

export interface SessionListProps {
  sessions: AssistantSession[];
  activeId: string | null;
  query: string;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onExport: (id: string) => void;
  onSearch: (query: string) => void;
}

export function SessionList({
  sessions,
  activeId,
  query,
  onCreate,
  onSelect,
  onDelete,
  onRename,
  onExport,
  onSearch,
}: SessionListProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null);
  const [search, setSearch] = useState(query);
  const firstRender = useRef(true);

  // 外部清空搜索（例如切换页面后）时同步本地输入；相同值不会触发额外搜索。
  useEffect(() => {
    setSearch((current) => (current.trim() === query.trim() ? current : query));
  }, [query]);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const timer = window.setTimeout(() => onSearch(search), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search, onSearch]);

  const startRename = (session: AssistantSession) => {
    setEditing({ id: session.id, title: session.title });
    setConfirming(null);
  };

  const commitRename = () => {
    if (!editing) return;
    const title = editing.title.trim();
    if (title && title !== sessions.find((item) => item.id === editing.id)?.title) {
      onRename(editing.id, title);
    }
    setEditing(null);
  };

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
      <CardContent className="space-y-2">
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("assistant.sessions.searchPlaceholder")}
            aria-label={t("assistant.sessions.search")}
            className="h-8 pl-8 text-sm"
          />
          {search ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 text-muted-foreground"
              aria-label={t("assistant.sessions.clearSearch")}
              title={t("assistant.sessions.clearSearch")}
              onClick={() => {
                setSearch("");
                onSearch("");
              }}
            >
              <X />
            </Button>
          ) : null}
        </div>

        {sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/40 p-4 text-center">
            <p className="eh-small font-medium">
              {query ? t("assistant.sessions.noResults") : t("assistant.sessions.empty")}
            </p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {query
                ? t("assistant.sessions.noResultsDesc", { query })
                : t("assistant.sessions.emptyDesc")}
            </p>
          </div>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => {
              const active = session.id === activeId;
              if (editing?.id === session.id) {
                return (
                  <li key={session.id} className="rounded-lg border border-primary/40 p-1.5">
                    <Input
                      value={editing.title}
                      autoFocus
                      maxLength={120}
                      aria-label={t("assistant.sessions.rename")}
                      className="h-8 text-sm"
                      onChange={(event) =>
                        setEditing((current) =>
                          current ? { ...current, title: event.target.value } : current,
                        )
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          commitRename();
                        } else if (event.key === "Escape") {
                          setEditing(null);
                        }
                      }}
                    />
                    <div className="mt-1.5 flex justify-end gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={() => setEditing(null)}
                      >
                        <X data-icon="inline-start" />
                        {t("assistant.sessions.renameCancel")}
                      </Button>
                      <Button type="button" size="xs" onClick={commitRename}>
                        <Check data-icon="inline-start" />
                        {t("assistant.sessions.renameSave")}
                      </Button>
                    </div>
                  </li>
                );
              }
              return (
                <li key={session.id} className="group/session relative">
                  <button
                    type="button"
                    onClick={() => onSelect(session.id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full items-start gap-2.5 rounded-lg border px-2.5 py-2 pr-[5.5rem] text-left transition-colors",
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
                  <span className="absolute top-1.5 right-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover/session:opacity-100 focus-within:opacity-100">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t("assistant.sessions.rename")}
                      title={t("assistant.sessions.rename")}
                      onClick={() => startRename(session)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t("assistant.sessions.export")}
                      title={t("assistant.sessions.export")}
                      onClick={() => onExport(session.id)}
                    >
                      <Download />
                    </Button>
                    <Button
                      type="button"
                      variant={confirming === session.id ? "destructive" : "ghost"}
                      size="icon-xs"
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
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

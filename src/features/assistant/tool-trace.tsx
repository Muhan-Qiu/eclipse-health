import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  LoaderCircle,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "cn";
import type { ToolCallTrace } from "./types";

function compactArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args).map(([key, value]) => {
    const text =
      typeof value === "string" ? value : JSON.stringify(value ?? null) ?? "";
    return `${key}: ${text.length > 28 ? `${text.slice(0, 28)}…` : text}`;
  });
  const joined = parts.join(", ");
  return joined.length > 72 ? `${joined.slice(0, 72)}…` : joined || "—";
}

export function ToolTrace({ calls }: { calls: ToolCallTrace[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (calls.length === 0) return null;

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-border/70 bg-background/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
      >
        <Wrench className="size-3.5 text-muted-foreground" aria-hidden="true" />
        <span className="text-xs font-medium">{t("assistant.tools.title")}</span>
        <Badge variant="secondary" className="font-normal">
          {t("assistant.tools.callCount", { count: calls.length })}
        </Badge>
        <ChevronDown
          className={cn(
            "ml-auto size-3.5 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <ul className="border-t border-border/70">
          {calls.map((call) => {
            const isOpen = expanded === call.id;
            return (
              <li key={call.id} className="border-b border-border/50 last:border-b-0">
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : call.id)}
                  aria-expanded={isOpen}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/30"
                >
                  {call.pending ? (
                    <LoaderCircle
                      className="size-3.5 shrink-0 animate-spin text-muted-foreground"
                      aria-label={t("assistant.tools.running")}
                    />
                  ) : call.ok ? (
                    <CircleCheck
                      className="size-3.5 shrink-0 text-muted-foreground"
                      aria-label={t("assistant.tools.success")}
                    />
                  ) : (
                    <CircleAlert
                      className="size-3.5 shrink-0 text-destructive"
                      aria-label={t("assistant.tools.failed")}
                    />
                  )}
                  <code className="shrink-0 font-mono text-[11px] font-medium">
                    {call.name}
                  </code>
                  <span className="eh-caption truncate text-muted-foreground">
                    {compactArgs(call.args)}
                  </span>
                  <span className="eh-caption ml-auto shrink-0 font-mono tabular-nums text-muted-foreground">
                    {call.pending
                      ? t("assistant.tools.running")
                      : t("assistant.tools.duration", { ms: call.durationMs })}
                  </span>
                  {isOpen ? (
                    <ChevronDown className="size-3 shrink-0" aria-hidden="true" />
                  ) : (
                    <ChevronRight className="size-3 shrink-0" aria-hidden="true" />
                  )}
                </button>

                {isOpen ? (
                  <div className="space-y-2 bg-muted/20 px-3 pt-1 pb-3">
                    <div>
                      <p className="eh-caption text-muted-foreground">
                        {t("assistant.tools.args")}
                      </p>
                      <pre className="mt-1 max-h-56 overflow-auto rounded-md border border-border/60 bg-background p-2 font-mono text-[11px] leading-5 whitespace-pre-wrap">
                        {JSON.stringify(call.args, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <p className="eh-caption text-muted-foreground">
                        {t("assistant.tools.result")}
                      </p>
                      <p className="mt-0.5 text-xs">{call.resultSummary}</p>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

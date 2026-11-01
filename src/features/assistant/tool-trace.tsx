import { useEffect, useState } from "react";
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
import { baseUrl } from "@/lib/api/client";
import { cn } from "cn";
import type { ToolCallTrace } from "./types";

/** 与后端 llm/tools.py 的命名规则保持一致：m_<fnv1a32(moduleId)>_<slug(toolId)>。 */
const MODULE_TOOL_PREFIX = "m_";
const MODULE_TOOL_SLUG_LIMIT = 53;

interface ModuleToolLabel {
  moduleName: string;
  toolName: string;
}

function fnv1a32(value: string): string {
  let digest = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(value)) {
    digest ^= byte;
    digest = Math.imul(digest, 0x01000193) >>> 0;
  }
  return digest.toString(16).padStart(8, "0");
}

function slug(value: string): string {
  const cleaned = value.replace(/[^A-Za-z0-9_-]/g, "_").replace(/^_+|_+$/g, "");
  return (cleaned || "tool").slice(0, MODULE_TOOL_SLUG_LIMIT);
}

function moduleToolAlias(moduleId: string, toolId: string): string {
  return `${MODULE_TOOL_PREFIX}${fnv1a32(moduleId)}_${slug(toolId)}`;
}

// 一次会话内只拉一次贡献注册表；模块名/工具名来自后端，不在前端硬编码。
let labelsPromise: Promise<Map<string, ModuleToolLabel>> | null = null;

function loadModuleToolLabels(): Promise<Map<string, ModuleToolLabel>> {
  labelsPromise ??= fetch(`${baseUrl}/modules/contributions?type=tools`, {
    credentials: "omit",
    headers: { Accept: "application/json" },
  })
    .then(async (response) => {
      if (!response.ok) return new Map<string, ModuleToolLabel>();
      const body = (await response.json()) as { items?: unknown };
      const labels = new Map<string, ModuleToolLabel>();
      if (!Array.isArray(body.items)) return labels;
      for (const item of body.items as Array<Record<string, unknown>>) {
        const moduleId = item?.moduleId;
        const toolId = item?.id;
        if (typeof moduleId !== "string" || typeof toolId !== "string") continue;
        labels.set(moduleToolAlias(moduleId, toolId), {
          moduleName: typeof item.moduleName === "string" ? item.moduleName : moduleId,
          toolName: typeof item.name === "string" ? item.name : toolId,
        });
      }
      return labels;
    })
    .catch(() => new Map<string, ModuleToolLabel>());
  return labelsPromise;
}

function useModuleToolLabels(): Map<string, ModuleToolLabel> {
  const [labels, setLabels] = useState<Map<string, ModuleToolLabel>>(
    () => new Map<string, ModuleToolLabel>(),
  );
  useEffect(() => {
    let active = true;
    void loadModuleToolLabels().then((value) => {
      if (active) setLabels(value);
    });
    return () => {
      active = false;
    };
  }, []);
  return labels;
}

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
  const moduleLabels = useModuleToolLabels();

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
            const moduleLabel = call.name.startsWith(MODULE_TOOL_PREFIX)
              ? moduleLabels.get(call.name)
              : undefined;
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
                  {moduleLabel ? (
                    <>
                      <Badge variant="outline" className="shrink-0 font-normal">
                        {moduleLabel.moduleName}
                      </Badge>
                      <span className="shrink-0 text-[11px] text-muted-foreground">·</span>
                      <code className="shrink-0 font-mono text-[11px] font-medium">
                        {moduleLabel.toolName}
                      </code>
                    </>
                  ) : (
                    <code className="shrink-0 font-mono text-[11px] font-medium">
                      {call.name}
                    </code>
                  )}
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

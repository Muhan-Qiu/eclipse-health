import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import type { Transparency } from "./types";

function FieldChips({ items, muted = false }: { items: string[]; muted?: boolean }) {
  if (items.length === 0) return <p className="eh-caption text-muted-foreground">—</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className={
            muted
              ? "rounded-md border border-border/60 bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground line-through"
              : "rounded-md border border-border/70 bg-background px-1.5 py-0.5 font-mono text-[11px]"
          }
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function IdList({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="block break-all font-mono text-[11px]">{items.join(", ")}</span>
  );
}

export interface TransparencySheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transparency: Transparency | null;
}

export function TransparencySheet({
  open,
  onOpenChange,
  transparency,
}: TransparencySheetProps) {
  const { t } = useTranslation();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4" aria-hidden="true" />
            {t("assistant.transparency.title")}
          </SheetTitle>
          <SheetDescription>{t("assistant.transparency.description")}</SheetDescription>
        </SheetHeader>

        {transparency ? (
          <div className="space-y-4 overflow-y-auto px-6 pb-6">
            <div className="rounded-lg border border-border/70 bg-surface/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">
                  {transparency.provider.label}
                </span>
                <Badge variant="outline" className="font-normal">
                  {transparency.localOnly
                    ? t("assistant.transparency.localOnly")
                    : t("assistant.transparency.remote")}
                </Badge>
              </div>
              <p className="eh-caption mt-1 text-muted-foreground">
                {t("assistant.transparency.provider")} ·{" "}
                {t(`assistant.providers.kinds.${transparency.provider.kind}`)}
              </p>
              <p className="eh-caption mt-0.5 font-mono text-muted-foreground">
                {t("assistant.transparency.model")}: {transparency.model}
              </p>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border border-border/60 px-2.5 py-2">
                <p className="eh-caption text-muted-foreground">
                  {t("assistant.transparency.approxTokens")}
                </p>
                <p className="eh-num mt-0.5 text-lg">{transparency.approxTokens}</p>
              </div>
              <div className="rounded-lg border border-border/60 px-2.5 py-2">
                <p className="eh-caption text-muted-foreground">
                  {t("assistant.transparency.toolCalls")}
                </p>
                <p className="eh-num mt-0.5 text-lg">{transparency.toolCalls}</p>
              </div>
              <div className="rounded-lg border border-border/60 px-2.5 py-2">
                <p className="eh-caption text-muted-foreground">
                  {t("assistant.transparency.includeNotes")}
                </p>
                <p className="mt-1 text-xs font-medium">
                  {transparency.includeNotes
                    ? t("assistant.transparency.notesIncluded")
                    : t("assistant.transparency.notesExcluded")}
                </p>
              </div>
            </div>

            <div className="rounded-lg border border-border/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="eh-caption text-muted-foreground">
                  {t("assistant.transparency.usageTitle")}
                </p>
                <Badge variant="outline" className="font-normal">
                  {transparency.usage
                    ? t(`assistant.transparency.usageSource.${transparency.usage.source}`, {
                        defaultValue: transparency.usage.source,
                      })
                    : t("assistant.transparency.none")}
                </Badge>
              </div>
              <div className="mt-1.5 grid grid-cols-3 gap-2">
                {(
                  [
                    ["usagePrompt", transparency.usage?.promptTokens],
                    ["usageCompletion", transparency.usage?.completionTokens],
                    ["usageTotal", transparency.usage?.totalTokens],
                  ] as const
                ).map(([key, value]) => (
                  <div key={key}>
                    <p className="eh-caption text-muted-foreground">
                      {t(`assistant.transparency.${key}`)}
                    </p>
                    <p className="eh-num mt-0.5 text-base">
                      {value ?? "—"}
                    </p>
                  </div>
                ))}
              </div>
              <p className="eh-caption mt-1 text-muted-foreground">
                {t("assistant.transparency.usageHint")}
              </p>
            </div>

            <Separator />

            <section className="space-y-2">
              <h3 className="eh-caption text-muted-foreground">
                {t("assistant.transparency.sentTitle")}
              </h3>
              <FieldChips items={transparency.sentFields} />
            </section>

            <section className="space-y-2">
              <h3 className="eh-caption text-muted-foreground">
                {t("assistant.transparency.notSentTitle")}
              </h3>
              <FieldChips items={transparency.redactions} muted />
            </section>

            <Separator />

            <section className="space-y-1.5">
              <h3 className="eh-caption text-muted-foreground">
                {t("assistant.transparency.recordIds")}
              </h3>
              <IdList items={transparency.recordIds} />
              <h3 className="eh-caption pt-1 text-muted-foreground">
                {t("assistant.transparency.analysisIds")}
              </h3>
              <IdList items={transparency.analysisIds} />
            </section>

            <p className="eh-caption rounded-lg bg-muted/40 p-2.5 text-muted-foreground">
              {t("assistant.transparency.note")}
            </p>
          </div>
        ) : (
          <p className="px-6 text-sm text-muted-foreground">
            {t("assistant.transparency.none")}
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}

import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Lightbulb, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "cn";
import type { SuggestionList } from "@/lib/api/types";

const MAX_ITEMS = 2;

export function SuggestionCard({
  suggestions,
  loading,
  error,
  className,
}: {
  suggestions: SuggestionList | undefined;
  loading: boolean;
  error: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const items = (suggestions?.items ?? []).slice(0, MAX_ITEMS);

  const talkToCoach = (prompt: string) => {
    // 助手页（G3/G4）读取 query 后填入输入框，不自动发送。
    navigate(`/assistant?prompt=${encodeURIComponent(prompt)}&new=1`);
  };

  return (
    <Card className={cn("eh-lift", className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("dashboard.suggestions.title")}</CardTitle>
        <CardDescription>{t("dashboard.suggestions.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : error || items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/60 px-4 py-5">
            <p className="eh-small font-medium">
              {t("dashboard.suggestions.emptyTitle")}
            </p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("dashboard.suggestions.emptyDesc")}
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-xl border border-border bg-subtle/40 p-3"
              >
                <div className="flex items-start gap-2">
                  <Lightbulb
                    className={cn(
                      "mt-0.5 size-4 shrink-0",
                      item.severity === "attention" ? "text-warning" : "text-signal",
                    )}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="eh-small">{item.text}</p>
                    <p
                      className={cn(
                        "eh-caption mt-1",
                        item.severity === "attention"
                          ? "text-warning"
                          : "text-muted-foreground",
                      )}
                    >
                      {t(`dashboard.suggestions.severity.${item.severity}`)}
                    </p>
                  </div>
                </div>
                <div className="mt-2 flex justify-end">
                  <Button
                    variant="ghost"
                    size="xs"
                    className="-mr-1.5"
                    onClick={() => talkToCoach(item.prompt)}
                  >
                    <MessageCircle data-icon="inline-start" />
                    {t("dashboard.suggestions.talkToCoach")}
                    <ArrowRight data-icon="inline-end" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

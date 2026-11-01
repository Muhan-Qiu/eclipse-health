import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, DatabaseZap, Trash2 } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { MiniBarChart, MiniLineChart } from "./mini-chart";
import { cardColor, type CardData, type DashboardCard } from "./types";

interface CustomCardProps {
  card: DashboardCard;
  data?: CardData | null;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onDelete?: () => void;
  /** 草稿卡片的「添加 / 忽略」等动作。 */
  actions?: ReactNode;
  draft?: boolean;
  className?: string;
}

function seriesValues(data: CardData | null | undefined): number[] {
  if (!data) return [];
  return data.series
    .map((point) => point.value)
    .filter((value) => Number.isFinite(value));
}

function formatValue(value: number, locale: string): string {
  return formatNumber(value, locale, { maximumFractionDigits: 2 });
}

export function CustomCard({
  card,
  data,
  loading = false,
  error = false,
  onRetry,
  onDelete,
  actions,
  draft = false,
  className,
}: CustomCardProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const color = cardColor(card.colorToken);
  const values = seriesValues(data);
  const kindLabel = t(`dashboard.customCards.kinds.${card.kind}`);
  const aggregationLabel = t(
    `dashboard.customCards.aggregations.${card.aggregation}`,
  );
  const aria = t("dashboard.customCards.chartAria", {
    title: card.title,
    kind: kindLabel,
  });

  const value =
    data && data.hasData && data.value !== null
      ? card.kind === "blood-pressure" && data.secondaryValue !== null
        ? `${formatValue(data.value, locale)}/${formatValue(
            data.secondaryValue,
            locale,
          )}`
        : formatValue(data.value, locale)
      : null;

  return (
    <Card
      className={cn(
        "h-full",
        draft && "border-dashed border-accent/60 bg-subtle/30",
        className,
      )}
    >
      <CardHeader>
        <CardTitle className="flex min-w-0 items-center gap-2 truncate">
          <span className="truncate">{card.title}</span>
          {draft ? (
            <Badge variant="outline" className="shrink-0 font-normal">
              {t("dashboard.customCards.draftBadge")}
            </Badge>
          ) : null}
        </CardTitle>
        <CardDescription className="truncate">
          {t("dashboard.customCards.basedOn", {
            kind: kindLabel,
            aggregation: aggregationLabel,
            days: card.windowDays,
          })}
        </CardDescription>
        <CardAction>
          <div className="flex items-center gap-1">
            {actions}
            {onDelete ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label={t("dashboard.customCards.delete")}
                onClick={onDelete}
              >
                <Trash2 />
              </Button>
            ) : null}
          </div>
        </CardAction>
      </CardHeader>

      <CardContent className="space-y-3">
        {loading ? (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : error ? (
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-start gap-2">
              <AlertCircle
                className="mt-0.5 size-4 shrink-0 text-destructive"
                aria-hidden="true"
              />
              <p className="eh-caption text-destructive">
                {t("dashboard.customCards.loadError")}
              </p>
            </div>
            {onRetry ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onRetry}
              >
                {t("common.retry")}
              </Button>
            ) : null}
          </div>
        ) : !data || !data.hasData ? (
          <div className="flex min-h-24 flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-surface/60 px-4 py-4 text-center">
            <DatabaseZap
              className="size-5 text-muted-foreground"
              aria-hidden="true"
            />
            <p className="eh-caption font-medium">
              {t("dashboard.customCards.emptyTitle")}
            </p>
            <p className="eh-caption text-muted-foreground">
              {t("dashboard.customCards.emptyDesc", { kind: kindLabel })}
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-end justify-between gap-3">
              <p className="flex min-w-0 items-baseline gap-1.5">
                <span
                  className={cn(
                    "eh-num leading-none font-medium",
                    card.view === "stat" ? "text-3xl" : "text-2xl",
                  )}
                  style={{ color }}
                >
                  {value ?? "—"}
                </span>
                {data.unit ? (
                  <span className="eh-caption text-muted-foreground">
                    {data.unit}
                  </span>
                ) : (
                  <Badge
                    variant="outline"
                    className="font-normal text-muted-foreground"
                  >
                    {t("dashboard.customCards.noUnit")}
                  </Badge>
                )}
              </p>
              <span className="eh-caption shrink-0 text-muted-foreground">
                {t("dashboard.customCards.sampleCount", {
                  count: data.sampleCount,
                })}
              </span>
            </div>

            {card.view === "sparkline" && values.length >= 2 ? (
              <svg
                viewBox="0 0 120 32"
                preserveAspectRatio="none"
                role="img"
                aria-label={aria}
                className="h-10 w-full"
              >
                <polyline
                  points={values
                    .map((point, index) => {
                      const min = Math.min(...values);
                      const max = Math.max(...values);
                      const span = max - min || 1;
                      const x = (index / Math.max(values.length - 1, 1)) * 120;
                      const y = 32 - 3 - ((point - min) / span) * (32 - 6);
                      return `${x.toFixed(2)},${y.toFixed(2)}`;
                    })
                    .join(" ")}
                  pathLength={1}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
            ) : null}

            {card.view === "line" && values.length >= 2 ? (
              <MiniLineChart values={values} color={color} ariaLabel={aria} />
            ) : null}

            {card.view === "bar" && values.length >= 1 ? (
              <MiniBarChart values={values} color={color} ariaLabel={aria} />
            ) : null}

            {(card.view === "line" || card.view === "bar") &&
            values.length < 2 ? (
              <p className="eh-caption text-muted-foreground">
                {t("dashboard.customCards.insufficient")}
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

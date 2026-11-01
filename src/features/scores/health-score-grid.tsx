import { useTranslation } from "react-i18next";
import { Activity, Moon, Scale, Stethoscope, HeartPulse, type LucideIcon } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AnimatedNumber } from "@/components/common/animated-number";
import { cn } from "cn";
import { formatDateTime, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import type { HealthScores, ScoreCategory, ScoreGrade } from "@/lib/api/types";

const CATEGORY_ICON: Record<string, LucideIcon> = {
  heart: HeartPulse,
  sleep: Moon,
  weight: Scale,
  activity: Activity,
  "blood-pressure": Stethoscope,
};

/** 等级不只靠颜色：同时显示文字，色弱用户也能读。 */
const GRADE_CLASS: Record<ScoreGrade, string> = {
  excellent: "text-success",
  good: "text-signal",
  fair: "text-warning",
  attention: "text-danger",
  unknown: "text-muted-foreground",
};

function CategoryTile({ category }: { category: ScoreCategory }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const Icon = CATEGORY_ICON[category.id] ?? HeartPulse;
  const label = t(`dashboard.scores.categories.${category.id}`, {
    defaultValue: category.label,
  });
  return (
    <div className="rounded-xl border border-border bg-subtle/40 p-3">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" />
        <span className="eh-caption truncate">{label}</span>
      </div>
      <p className="eh-num mt-1.5 text-2xl leading-7 font-medium">
        {formatNumber(category.score, locale, { maximumFractionDigits: 0 })}
      </p>
      <p className={cn("eh-caption mt-0.5", GRADE_CLASS[category.grade])}>
        {t(`dashboard.scores.grades.${category.grade}`)}
      </p>
    </div>
  );
}

export function HealthScoreGrid({
  scores,
  loading,
  error,
  className,
}: {
  scores: HealthScores | undefined;
  loading: boolean;
  error: boolean;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);

  const categories = (scores?.categories ?? []).filter(
    (category) => category.grade !== "unknown",
  );
  const hasScores = scores !== undefined && scores.overall !== null;
  const insufficient = error || (!loading && (!hasScores || categories.length === 0));

  const missingText = (scores?.missing ?? [])
    .map((item) =>
      t(`dashboard.scores.categories.${item.id}`, { defaultValue: item.id }),
    )
    .join(t("dashboard.scores.missingSeparator"));

  return (
    <Card className={cn("eh-lift", className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("dashboard.scores.title")}</CardTitle>
        <CardDescription>
          {scores?.generatedAt
            ? t("dashboard.scores.generatedAt", {
                time: formatDateTime(scores.generatedAt, locale),
              })
            : t("dashboard.scores.description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="h-16 w-40" />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-24 w-full" />
              ))}
            </div>
          </div>
        ) : insufficient ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/60 px-4 py-5">
            <p className="eh-small font-medium">{t("dashboard.scores.insufficient")}</p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("dashboard.scores.insufficientDesc")}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-end gap-3">
              <p className="eh-metric text-foreground" aria-label={t("dashboard.scores.overall")}>
                <AnimatedNumber
                  value={scores?.overall ?? null}
                  format={(value) =>
                    formatNumber(value, locale, { maximumFractionDigits: 0 })
                  }
                />
              </p>
              <div className="pb-1.5">
                <p className="eh-caption text-muted-foreground">
                  {t("dashboard.scores.overall")}
                </p>
                <p className="eh-caption text-muted-foreground">
                  {t("dashboard.scores.overallHint")}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
              {categories.map((category) => (
                <CategoryTile key={category.id} category={category} />
              ))}
            </div>

            {missingText ? (
              <p className="eh-caption text-muted-foreground">
                {t("dashboard.scores.missing", { items: missingText })}
              </p>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

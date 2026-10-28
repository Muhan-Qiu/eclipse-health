import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Watch } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DemoBadge } from "@/components/common/demo-badge";
import { formatDateTime, formatDuration, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";
import type { RecordSummary } from "@/lib/api/types";

export function RecordRow({ record }: { record: RecordSummary }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const tagLabel = useTagLabel();

  return (
    <Link
      to={`/records/${record.id}`}
      className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent focus-visible:bg-accent"
    >
      <div
        className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-subtle text-muted-foreground"
        aria-hidden="true"
      >
        <Watch className="size-4" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium">
            {formatDateTime(record.recordedAt, locale)}
          </p>
          {record.isDemo ? <DemoBadge /> : null}
          {record.status !== "ready" ? (
            <Badge
              variant={record.status === "failed" ? "destructive" : "outline"}
              aria-label={t("a11y.status", {
                status: t(`records.status.${record.status}`),
              })}
            >
              {t(`records.status.${record.status}`)}
            </Badge>
          ) : null}
        </div>
        <p className="eh-caption mt-0.5 truncate text-muted-foreground">
          {record.device.model} · {record.leads.join(" / ")} ·{" "}
          {formatNumber(record.sampleRateHz, locale)} Hz
        </p>
      </div>

      <div className="hidden items-center gap-1.5 sm:flex">
        {record.tags.slice(0, 2).map((tag) => (
          <Badge key={tag} variant="secondary" className="font-normal">
            {tagLabel(tag)}
          </Badge>
        ))}
      </div>

      <span className="eh-num hidden text-xs text-muted-foreground md:inline">
        {formatDuration(record.durationSec, locale)}
      </span>

      <ArrowRight
        className="size-4 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
    </Link>
  );
}

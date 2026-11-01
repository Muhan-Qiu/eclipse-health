import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity,
  ArrowRight,
  Circle,
  CircleAlert,
  CircleCheck,
  FileText,
  LoaderCircle,
  Star,
  Watch,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { DemoBadge } from "@/components/common/demo-badge";
import { useToggleFavorite } from "@/lib/api/queries";
import { formatDateTime, formatDuration, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";
import type { LatestAnalysisStatus, RecordSummary } from "@/lib/api/types";

const VENDOR_ICON = {
  apple: Watch,
  samsung: Watch,
  huawei: Watch,
  generic: FileText,
} as const;

interface StatusPresentation {
  icon: LucideIcon;
  variant: "outline" | "secondary" | "destructive";
  tone: string;
}

/** 颜色 + 图标 + 文字三重表达，颜色不单独承载信息。 */
const STATUS_PRESENTATION: Record<LatestAnalysisStatus, StatusPresentation> = {
  none: { icon: Circle, variant: "outline", tone: "text-muted-foreground" },
  queued: { icon: LoaderCircle, variant: "outline", tone: "text-muted-foreground" },
  running: { icon: LoaderCircle, variant: "outline", tone: "text-primary" },
  completed: { icon: CircleCheck, variant: "secondary", tone: "text-primary" },
  failed: { icon: CircleAlert, variant: "destructive", tone: "" },
};

export interface RecordSelection {
  selected: boolean;
  /** 已选满 2 条时为 true；选中项自身仍可取消。 */
  disabled: boolean;
  onToggle: (id: string) => void;
}

export function RecordRow({
  record,
  selection,
}: {
  record: RecordSummary;
  selection?: RecordSelection;
}) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const tagLabel = useTagLabel();
  const toggleFavorite = useToggleFavorite();
  const dateLabel = formatDateTime(record.recordedAt, locale);
  const Icon = VENDOR_ICON[record.device.vendor] ?? Activity;
  const status =
    STATUS_PRESENTATION[record.analysisStatus] ?? STATUS_PRESENTATION.none;
  const StatusIcon = status.icon;

  return (
    <div className="flex items-center gap-3 px-5 py-3 transition-colors duration-[120ms] hover:bg-accent focus-within:bg-accent">
      {selection ? (
        <input
          type="checkbox"
          className="size-4 shrink-0 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-40"
          checked={selection.selected}
          disabled={selection.disabled && !selection.selected}
          onChange={() => selection.onToggle(record.id)}
          aria-label={t("records.select", {
            date: formatDateTime(record.recordedAt, locale),
          })}
        />
      ) : null}

      <Link
        to={`/records/${record.id}`}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-sm focus-visible:outline-none"
      >
        <div
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-subtle text-muted-foreground"
          aria-hidden="true"
        >
          <Icon className="size-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="shrink-0 truncate text-sm font-medium">
              {formatDateTime(record.recordedAt, locale)}
            </p>
            {record.isDemo ? <DemoBadge /> : null}
            {record.isSample ? (
              <Badge
                variant="outline"
                className="border-dashed font-normal text-muted-foreground"
                aria-label={t("a11y.sampleData")}
              >
                {t("records.sampleBadge")}
              </Badge>
            ) : null}
            <Badge
              variant={status.variant}
              className={cn("gap-1 font-normal", status.tone)}
              aria-label={t("a11y.status", {
                status: t(`recordStatus.${record.analysisStatus}`),
              })}
            >
              <StatusIcon className="size-3" aria-hidden="true" />
              {t(`recordStatus.${record.analysisStatus}`)}
            </Badge>
          </div>
          <p className="eh-caption mt-0.5 truncate text-muted-foreground">
            {record.device.model || t("records.localFile")} ·{" "}
            {record.leads.join(" / ") || "—"} ·{" "}
            {record.sampleRateHz > 0
              ? `${formatNumber(record.sampleRateHz, locale)} Hz`
              : "—"}
            {record.latestAnalyzedAt
              ? ` · ${t("records.latestAnalyzed", {
                  time: formatDateTime(record.latestAnalyzedAt, locale),
                })}`
              : null}
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
          {record.durationSec > 0
            ? formatDuration(record.durationSec, locale)
            : "—"}
        </span>

        <ArrowRight
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      </Link>

      <button
        type="button"
        aria-pressed={record.favorite}
        aria-label={
          record.favorite
            ? t("records.unfavorite", { date: dateLabel })
            : t("records.favorite", { date: dateLabel })
        }
        onClick={() =>
          toggleFavorite.mutate({
            id: record.id,
            favorite: !record.favorite,
          })
        }
        className="grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground transition-[background-color,color,transform] duration-[120ms] hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none active:scale-90"
      >
        <Star
          className={cn(
            "size-4 transition-colors",
            record.favorite && "eh-star-pop fill-current text-primary",
          )}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}

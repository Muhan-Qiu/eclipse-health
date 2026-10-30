import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import type { Quality, QualitySegment } from "@/lib/api/types";
import { formatClock, qualityLevel, type QualityLevel } from "@/lib/waveform";

const LEVEL_CLASS: Record<QualityLevel, string> = {
  good: "bg-success",
  fair: "bg-warning",
  poor: "bg-danger",
};

const LEVEL_BADGE: Record<QualityLevel, "secondary" | "outline" | "destructive"> = {
  good: "secondary",
  fair: "outline",
  poor: "destructive",
};

export interface QualityLegendProps {
  quality?: Quality | null;
  onFocus?: (startSec: number, endSec: number) => void;
  className?: string;
  height?: number;
}

function reasonFor(segment: QualitySegment, quality: Quality): string {
  const reasons = quality.warnings
    .filter((warning) => {
      const start = warning.startSec;
      const end = warning.endSec;
      if (start === null || start === undefined || end === null || end === undefined) {
        return false;
      }
      return start < segment.endSec && end > segment.startSec;
    })
    .map((warning) => warning.message || warning.code)
    .filter(Boolean);
  return [...new Set(reasons)].join("；");
}

/**
 * 质量区段图例 + 列表（B4-05）：与波形底色阈值一致，点击定位。
 * 颜色不单独承载信息，同时给出等级文字与百分比。
 */
export function QualityLegend({
  quality,
  onFocus,
  className,
  height = 192,
}: QualityLegendProps) {
  const { t } = useTranslation();
  const segments = useMemo(() => {
    const rows = [...(quality?.segments ?? [])];
    rows.sort((a, b) => a.quality - b.quality || a.startSec - b.startSec);
    return rows;
  }, [quality]);
  const listed = segments.slice(0, 100);

  return (
    <section
      className={cn("rounded-lg border border-border bg-surface", className)}
      aria-label={t("qualityLegend.title")}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-2.5 py-2">
        <h4 className="eh-caption text-foreground">{t("qualityLegend.title")}</h4>
        <span className="eh-caption eh-num text-muted-foreground">
          {t("qualityLegend.count", { count: segments.length })}
        </span>
      </header>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2.5 py-2 text-[11px] text-muted-foreground">
        {(["good", "fair", "poor"] as QualityLevel[]).map((level) => (
          <span key={level} className="flex items-center gap-1">
            <span
              className={cn("inline-block size-2.5 rounded-sm", LEVEL_CLASS[level])}
              aria-hidden="true"
            />
            {t(`qualityLegend.levels.${level}`)}
          </span>
        ))}
        <span className="ml-auto">{t("qualityLegend.thresholds")}</span>
      </div>

      {segments.length === 0 ? (
        <p className="px-2.5 pb-3 text-xs text-muted-foreground">
          {t("qualityLegend.empty")}
        </p>
      ) : (
        <div className="overflow-y-auto px-1.5 pb-1.5" style={{ maxHeight: height }}>
          <div className="grid grid-cols-[minmax(76px,1fr)_58px_44px] gap-1 px-1 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            <span>{t("qualityLegend.columns.time")}</span>
            <span>{t("qualityLegend.columns.level")}</span>
            <span className="text-right">{t("qualityLegend.columns.score")}</span>
          </div>
          {listed.map((segment, index) => {
            const level = qualityLevel(segment.quality);
            const reason = quality ? reasonFor(segment, quality) : "";
            return (
              <button
                type="button"
                key={`${segment.startSec}-${segment.endSec}-${index}`}
                onClick={() => onFocus?.(segment.startSec, segment.endSec)}
                className="grid w-full grid-cols-[minmax(76px,1fr)_58px_44px] items-center gap-1 rounded-md px-1 py-1 text-left text-[11px] eh-num tabular-nums hover:bg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title={
                  reason ||
                  t("qualityLegend.focus", {
                    start: formatClock(segment.startSec),
                    end: formatClock(segment.endSec),
                  })
                }
                aria-label={t("qualityLegend.focus", {
                  start: formatClock(segment.startSec),
                  end: formatClock(segment.endSec),
                })}
              >
                <span>
                  {formatClock(segment.startSec)} – {formatClock(segment.endSec)}
                  {reason ? (
                    <span className="block truncate text-[10px] font-normal text-muted-foreground">
                      {reason}
                    </span>
                  ) : null}
                </span>
                <Badge variant={LEVEL_BADGE[level]} className="h-4 w-fit px-1 text-[10px]">
                  {t(`qualityLegend.levels.${level}`)}
                </Badge>
                <span className="text-right">{Math.round(segment.quality * 100)}%</span>
              </button>
            );
          })}
          {segments.length > listed.length ? (
            <p className="px-1 py-1 text-[10px] text-muted-foreground">
              {t("qualityLegend.more", { count: segments.length - listed.length })}
            </p>
          ) : null}
        </div>
      )}

      <p className="border-t border-border px-2.5 py-1.5 text-[10px] text-muted-foreground">
        {t("qualityLegend.footer")}
      </p>
    </section>
  );
}

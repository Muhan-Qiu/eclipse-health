import { useTranslation } from "react-i18next";
import { cn } from "cn";
import type { Beat, Measurement } from "@/lib/api/types";
import { formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { measurementsByCode } from "./measurement-list";

const CLASS_ORDER = ["N", "SVEB", "VEB", "F"] as const;

const CLASS_COLOR: Record<string, string> = {
  N: "bg-signal",
  SVEB: "bg-info",
  VEB: "bg-warning",
  F: "bg-danger",
};

const RATIO_CODE: Record<string, string> = {
  N: "n_ratio",
  SVEB: "svb_ratio",
  VEB: "veb_ratio",
  F: "f_ratio",
};

function Bar({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: number;
  colorClass: string;
}) {
  const { i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const width = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="eh-caption text-muted-foreground">{label}</span>
        <span className="eh-num text-xs tabular-nums">
          {formatNumber(value, locale, { maximumFractionDigits: 1 })}%
        </span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-subtle"
        role="presentation"
      >
        <div
          className={cn("h-full rounded-full transition-[width]", colorClass)}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

export function ClassRatioBars({ measurements }: { measurements: Measurement[] }) {
  const { t } = useTranslation();
  const byCode = measurementsByCode(measurements);
  const values = CLASS_ORDER.map((label) => {
    const measurement = byCode.get(RATIO_CODE[label]);
    return { label, value: measurement?.value ?? 0 };
  });
  const total = values.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) return null;

  return (
    <div className="space-y-2.5">
      <h4 className="eh-caption text-muted-foreground">
        {t("analysis.classes.title")}
      </h4>
      {values.map((item) => (
        <Bar
          key={item.label}
          label={t(`analysis.classes.${item.label}`)}
          value={item.value}
          colorClass={CLASS_COLOR[item.label]}
        />
      ))}
    </div>
  );
}

export function BeatProbabilityBars({ beat }: { beat: Beat }) {
  const { t } = useTranslation();
  const values = CLASS_ORDER.map((label) => ({
    label,
    value: (beat.probabilities[label] ?? 0) * 100,
  }));
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {values.map((item) => (
        <Bar
          key={item.label}
          label={t(`analysis.classes.${item.label}`)}
          value={item.value}
          colorClass={CLASS_COLOR[item.label]}
        />
      ))}
    </div>
  );
}

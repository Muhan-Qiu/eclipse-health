import { useTranslation } from "react-i18next";
import { Info, TriangleAlert } from "lucide-react";
import { cn } from "cn";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Measurement } from "@/lib/api/types";
import { formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";

const GROUPS: { key: string; codes: string[] }[] = [
  { key: "rate", codes: ["heart_rate_mean", "heart_rate_min", "heart_rate_max", "rr_mean"] },
  { key: "hrv", codes: ["sdnn", "rmssd", "pnn50"] },
  {
    key: "morphology",
    codes: ["qrs_duration", "pr_interval", "qt_interval", "qtc"],
  },
  { key: "rhythm", codes: ["n_ratio", "svb_ratio", "veb_ratio", "f_ratio"] },
];

const CORE_ORDER = GROUPS.flatMap((group) => group.codes);

export function measurementValue(
  measurement: Measurement,
  locale: string,
): string {
  if (measurement.value === null || measurement.value === undefined) return "—";
  const digits = Math.abs(measurement.value) >= 100 ? 0 : 1;
  return formatNumber(measurement.value, locale, {
    maximumFractionDigits: digits,
  });
}

export function measurementsByCode(
  measurements: Measurement[],
): Map<string, Measurement> {
  return new Map(measurements.map((measurement) => [measurement.code, measurement]));
}

interface MeasurementListProps {
  measurements: Measurement[];
  className?: string;
}

export function MeasurementList({ measurements, className }: MeasurementListProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const byCode = measurementsByCode(measurements);
  const extra = measurements.filter((item) => !CORE_ORDER.includes(item.code));

  return (
    <div className={cn("space-y-4", className)}>
      {GROUPS.map((group) => {
        const items = group.codes
          .map((code) => byCode.get(code))
          .filter((item): item is Measurement => Boolean(item));
        if (!items.length) return null;
        return (
          <section key={group.key}>
            <h4 className="eh-caption mb-1.5 text-muted-foreground">
              {t(`measurements.groups.${group.key}`)}
            </h4>
            <ul className="divide-y divide-border">
              {items.map((measurement) => (
                <MeasurementRow
                  key={measurement.code}
                  measurement={measurement}
                  locale={locale}
                />
              ))}
            </ul>
          </section>
        );
      })}

      {extra.length ? (
        <section>
          <h4 className="eh-caption mb-1.5 text-muted-foreground">
            {t("measurements.groups.other")}
          </h4>
          <ul className="divide-y divide-border">
            {extra.map((measurement) => (
              <MeasurementRow
                key={measurement.code}
                measurement={measurement}
                locale={locale}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function MeasurementRow({
  measurement,
  locale,
}: {
  measurement: Measurement;
  locale: string;
}) {
  const { t } = useTranslation();
  const label = t(`measurements.codes.${measurement.code}`, {
    defaultValue: measurement.label,
  });
  const explanation = t(`measurements.explanations.${measurement.code}.text`, {
    defaultValue: "",
  });
  const range = t(`measurements.explanations.${measurement.code}.range`, {
    defaultValue: "",
  });
  const unavailable = measurement.value === null || measurement.value === undefined;
  const lowConfidence =
    measurement.confidence !== null && measurement.confidence < 0.6;

  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="eh-small text-foreground">{label}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={t("measurements.explain", { label })}
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs flex-col items-start gap-1">
              <span>
                {explanation ||
                  t("measurements.explanations.unknown", {
                    defaultValue: "该指标的解读将在后续版本补充。",
                  })}
              </span>
              {range ? (
                <span className="text-background/80">
                  {t("measurements.normalRange")}: {range}
                </span>
              ) : null}
              {measurement.method ? (
                <span className="text-background/70">
                  {t("measurements.method", { method: measurement.method })}
                </span>
              ) : null}
            </TooltipContent>
          </Tooltip>
          {lowConfidence ? (
            <span
              className="text-warning"
              title={t("measurements.lowConfidence")}
            >
              <TriangleAlert className="size-3.5" aria-label={t("measurements.lowConfidence")} />
            </span>
          ) : null}
        </div>
        <p className="eh-caption mt-0.5 text-muted-foreground">
          {unavailable ? t("measurements.unavailable") : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <span
          className={cn(
            "eh-num text-base tabular-nums",
            unavailable ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {measurementValue(measurement, locale)}
        </span>
        {measurement.value !== null && measurement.unit ? (
          <span className="eh-caption ml-1 text-muted-foreground">
            {measurement.unit}
          </span>
        ) : null}
      </div>
    </li>
  );
}

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Progress } from "@/components/ui/progress";
import { Sparkline } from "@/components/common/sparkline";
import { formatNumber } from "@/lib/format";
import type { ModuleWidget, WidgetViewType } from "../types";
import { readValuePath } from "./value-path";

const VIEW_TYPES: readonly WidgetViewType[] = [
  "stat",
  "sparkline",
  "list",
  "progress",
  "text",
];

const LIST_LIMIT = 5;

function isWidgetViewType(type: string): type is WidgetViewType {
  return (VIEW_TYPES as readonly string[]).includes(type);
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function primitiveText(value: unknown, locale: string): string | null {
  if (typeof value === "string") return value.trim() === "" ? null : value;
  if (typeof value === "number") {
    return Number.isFinite(value)
      ? formatNumber(value, locale, { maximumFractionDigits: 2 })
      : null;
  }
  if (typeof value === "boolean") return String(value);
  return null;
}

/** 折线既接受 `[1,2,3]`，也接受 `[{ value: 1 }, …]`，其余形状视为无数据。 */
function numberSeries(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  const series: number[] = [];
  for (const item of value) {
    const direct = finiteNumber(item);
    if (direct !== null) {
      series.push(direct);
      continue;
    }
    if (item !== null && typeof item === "object") {
      const nested = finiteNumber((item as Record<string, unknown>).value);
      if (nested !== null) series.push(nested);
    }
  }
  return series;
}

interface ListEntry {
  label: string;
  value: string | null;
}

function listEntry(item: unknown, locale: string): ListEntry | null {
  const direct = primitiveText(item, locale);
  if (direct !== null) return { label: direct, value: null };
  if (item === null || typeof item !== "object" || Array.isArray(item)) return null;

  const record = item as Record<string, unknown>;
  const value = primitiveText(
    record.value ?? record.amount ?? record.count,
    locale,
  );
  const label = primitiveText(
    record.label ?? record.name ?? record.title ?? record.text ?? record.key,
    locale,
  );
  if (label === null && value === null) return null;
  return { label: label ?? value ?? "", value: label ? value : null };
}

interface WidgetViewProps {
  widget: ModuleWidget;
  data: unknown;
  locale: string;
}

export function WidgetView({ widget, data, locale }: WidgetViewProps) {
  const { t } = useTranslation();
  const view = widget.view;
  const viewType = view.type;

  if (!isWidgetViewType(viewType)) {
    return (
      <p className="eh-caption text-muted-foreground">
        {t("moduleUi.widgets.unsupported", { type: view.type })}
      </p>
    );
  }

  const value = readValuePath(data, view.valuePath);
  const missing = (
    <span className="eh-caption text-muted-foreground">
      {t("moduleUi.widgets.noData")}
    </span>
  );

  let body: ReactNode = missing;
  switch (viewType) {
    case "stat": {
      const number = finiteNumber(value);
      const text = number === null ? primitiveText(value, locale) : null;
      body =
        number !== null ? (
          <p className="flex items-baseline gap-1.5">
            <span className="eh-num text-3xl leading-9 font-medium">
              {formatNumber(number, locale, { maximumFractionDigits: 2 })}
            </span>
            {view.unit ? (
              <span className="eh-caption text-muted-foreground">{view.unit}</span>
            ) : null}
          </p>
        ) : text !== null ? (
          <p className="eh-num text-2xl leading-8 font-medium break-words">{text}</p>
        ) : (
          missing
        );
      break;
    }

    case "sparkline": {
      const series = numberSeries(value);
      body =
        series.length > 0 ? (
          <div className="flex items-end justify-between gap-3">
            <Sparkline
              values={series}
              ariaLabel={t("moduleUi.widgets.sparklineAria", { title: widget.title })}
              className="h-10 w-full"
            />
            {view.unit ? (
              <span className="eh-caption shrink-0 text-muted-foreground">
                {view.unit}
              </span>
            ) : null}
          </div>
        ) : (
          missing
        );
      break;
    }

    case "list": {
      const items = Array.isArray(value) ? value : [];
      const entries = items
        .slice(0, LIST_LIMIT)
        .map((item) => listEntry(item, locale))
        .filter((entry): entry is ListEntry => entry !== null);
      body =
        entries.length > 0 ? (
          <div className="space-y-1.5">
            <ul className="space-y-1.5">
              {entries.map((entry, index) => (
                <li
                  key={`${index}-${entry.label}`}
                  className="flex items-baseline justify-between gap-3 text-sm"
                >
                  <span className="truncate">{entry.label}</span>
                  {entry.value ? (
                    <span className="eh-num shrink-0 text-muted-foreground">
                      {entry.value}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
            {items.length > LIST_LIMIT ? (
              <p className="eh-caption text-muted-foreground">
                {t("moduleUi.widgets.moreItems", {
                  count: items.length - LIST_LIMIT,
                })}
              </p>
            ) : null}
          </div>
        ) : (
          missing
        );
      break;
    }

    case "progress": {
      const number = finiteNumber(value);
      if (number === null) {
        body = missing;
        break;
      }
      const min = finiteNumber(view.min) ?? 0;
      const max = finiteNumber(view.max) ?? 100;
      const span = max - min;
      const ratio = span > 0 ? (number - min) / span : 0;
      const percent = Math.min(100, Math.max(0, ratio * 100));
      body = (
        <div className="space-y-2">
          <p className="flex items-baseline gap-1.5">
            <span className="eh-num text-2xl leading-8 font-medium">
              {formatNumber(number, locale, { maximumFractionDigits: 2 })}
            </span>
            {view.unit ? (
              <span className="eh-caption text-muted-foreground">
                {view.unit}
              </span>
            ) : null}
          </p>
          <Progress
            value={percent}
            aria-valuenow={Math.round(percent)}
            aria-label={t("moduleUi.widgets.progressAria", {
              title: widget.title,
            })}
          />
        </div>
      );
      break;
    }

    case "text": {
      const text = primitiveText(value, locale);
      body =
        text !== null ? (
          <p className="text-sm leading-relaxed break-words whitespace-pre-line">
            {text}
          </p>
        ) : (
          missing
        );
      break;
    }
  }

  return (
    <div className="space-y-1.5">
      {view.label ? (
        <p className="eh-caption text-muted-foreground">{view.label}</p>
      ) : null}
      {body}
    </div>
  );
}

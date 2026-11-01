import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Progress } from "@/components/ui/progress";
import { Sparkline } from "@/components/common/sparkline";
import { formatNumber } from "@/lib/format";
import type { ModuleWidget } from "../types";
import { readValuePath } from "./value-path";

/** 受控视图白名单；未知类型只降级，不抛异常。 */
type LocalViewType =
  | "stat"
  | "sparkline"
  | "list"
  | "progress"
  | "text"
  | "bar"
  | "line"
  | "heatmap";

const VIEW_TYPES: readonly LocalViewType[] = [
  "stat",
  "sparkline",
  "list",
  "progress",
  "text",
  "bar",
  "line",
  "heatmap",
];

const LIST_LIMIT = 5;
const CHART_WIDTH = 240;
const CHART_HEIGHT = 72;
/** 热力图最多渲染 84 格，避免模块返回超长数组拖垮 DOM。 */
const HEATMAP_LIMIT = 84;
const HEATMAP_ROW = 7;

function isWidgetViewType(type: string): type is LocalViewType {
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

/** 折线/柱状既接受 `[1,2,3]`，也接受 `[{ value: 1 }, …]`，其余形状视为无数据。 */
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

/** 与数值序列一一对应的标签；缺失位置留空，不改变长度。 */
function labelSeries(value: unknown, count: number, locale: string): string[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, count).map((item) => {
    if (item !== null && typeof item === "object" && !Array.isArray(item)) {
      const record = item as Record<string, unknown>;
      return (
        primitiveText(
          record.label ?? record.name ?? record.date ?? record.time ?? record.text,
          locale,
        ) ?? ""
      );
    }
    return primitiveText(item, locale) ?? "";
  });
}

function sampleLabels(labels: string[], max = 6): string[] {
  if (labels.length <= max) return labels;
  const step = (labels.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, index) =>
    labels[Math.round(index * step)],
  );
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

/* ------------------------------------------------------------------ *
 * bar / line / heatmap · 纯 SVG / CSS，不引第三方图表库
 * ------------------------------------------------------------------ */

function BarChart({ values, ariaLabel }: { values: number[]; ariaLabel: string }) {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;
  const zeroY = CHART_HEIGHT - ((0 - min) / span) * CHART_HEIGHT;
  const slot = CHART_WIDTH / values.length;
  const barWidth = Math.max(slot * 0.62, 1);
  return (
    <svg
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="h-16 w-full"
    >
      {values.map((value, index) => {
        const y = CHART_HEIGHT - ((value - min) / span) * CHART_HEIGHT;
        const top = Math.min(y, zeroY);
        const height = Math.max(Math.abs(zeroY - y), value === 0 ? 0 : 1);
        const fill = index % 2 === 0 ? "var(--eh-chart-1)" : "var(--eh-signal)";
        return (
          <rect
            key={index}
            x={(index * slot + (slot - barWidth) / 2).toFixed(2)}
            y={top.toFixed(2)}
            width={barWidth.toFixed(2)}
            height={height.toFixed(2)}
            rx={1}
            fill={fill}
            opacity={0.9}
          />
        );
      })}
      <line
        x1={0}
        x2={CHART_WIDTH}
        y1={zeroY}
        y2={zeroY}
        stroke="var(--eh-grid-line)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function LineChart({ values, ariaLabel }: { values: number[]; ariaLabel: string }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const padding = 4;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * CHART_WIDTH;
      const y =
        CHART_HEIGHT -
        padding -
        ((value - min) / span) * (CHART_HEIGHT - padding * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="h-16 w-full"
    >
      <polyline
        points={points}
        pathLength={1}
        fill="none"
        stroke="var(--eh-signal)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        className="eh-sparkline__line"
      />
    </svg>
  );
}

interface HeatCell {
  value: number | null;
  label: string | null;
}

function heatRows(value: unknown, locale: string): HeatCell[][] {
  if (!Array.isArray(value) || value.length === 0) return [];
  if (Array.isArray(value[0])) {
    return (value as unknown[][])
      .filter((row) => Array.isArray(row))
      .map((row) =>
        row.map((cell, index) => ({
          value: finiteNumber(cell),
          label: String(index + 1),
        })),
      );
  }

  const cells: HeatCell[] = value.map((entry, index) => {
    if (entry !== null && typeof entry === "object" && !Array.isArray(entry)) {
      const record = entry as Record<string, unknown>;
      return {
        value: finiteNumber(record.value),
        label:
          primitiveText(
            record.date ?? record.label ?? record.time ?? record.day,
            locale,
          ) ?? String(index + 1),
      };
    }
    return { value: finiteNumber(entry), label: String(index + 1) };
  });
  const hasDates = cells.some((cell) => cell.label && !/^\d+$/.test(cell.label));
  const rowSize = hasDates ? HEATMAP_ROW : cells.length;
  const rows: HeatCell[][] = [];
  for (let index = 0; index < cells.length; index += rowSize) {
    rows.push(cells.slice(index, index + rowSize));
  }
  return rows;
}

function Heatmap({
  rows,
  ariaLabel,
}: {
  rows: HeatCell[][];
  ariaLabel: string;
}) {
  const numeric = rows
    .flat()
    .map((cell) => cell.value)
    .filter((value): value is number => value !== null);
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const span = max - min || 1;
  const columns = Math.max(...rows.map((row) => row.length));

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className="grid gap-1"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {rows.map((row, rowIndex) => (
        <div
          key={rowIndex}
          className="contents"
          style={{ display: "contents" }}
        >
          {row.map((cell, cellIndex) => {
            if (cell.value === null) {
              return (
                <span
                  key={cellIndex}
                  aria-hidden="true"
                  className="h-4 rounded-[3px] bg-subtle"
                />
              );
            }
            const ratio = (cell.value - min) / span;
            const opacity = 18 + Math.round(ratio * 82);
            const title =
              cell.label !== null
                ? `${cell.label}: ${formatNumber(cell.value, "en-US", {
                    maximumFractionDigits: 2,
                  })}`
                : undefined;
            return (
              <span
                key={cellIndex}
                aria-hidden="true"
                title={title}
                className="h-4 rounded-[3px]"
                style={{
                  backgroundColor: `color-mix(in srgb, var(--eh-signal) ${opacity}%, transparent)`,
                }}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

interface WidgetViewProps {
  widget: ModuleWidget;
  data: unknown;
  locale: string;
}

export function WidgetView({ widget, data, locale }: WidgetViewProps) {
  const { t } = useTranslation();
  const view = widget.view as typeof widget.view & {
    seriesPath?: string;
    labelPath?: string;
  };
  const viewType = view.type;

  if (!isWidgetViewType(viewType)) {
    return (
      <p className="eh-caption text-muted-foreground">
        {t("moduleUi.widgets.unsupported", { type: view.type })}
      </p>
    );
  }

  const value =
    typeof view.valuePath === "string"
      ? readValuePath(data, view.valuePath)
      : undefined;
  const seriesValue =
    typeof view.seriesPath === "string" && view.seriesPath.length > 0
      ? readValuePath(data, view.seriesPath)
      : value;
  const rawLabels =
    typeof view.labelPath === "string" && view.labelPath.length > 0
      ? readValuePath(data, view.labelPath)
      : undefined;
  const missing = (
    <span className="eh-caption text-muted-foreground">
      {t("moduleUi.widgets.noData")}
    </span>
  );
  const chartAria = t("moduleUi.widgets.sparklineAria", {
    title: widget.title,
  });

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
              ariaLabel={chartAria}
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

    case "bar":
    case "line": {
      const series = numberSeries(seriesValue);
      if (series.length === 0) {
        body = missing;
        break;
      }
      const labels = sampleLabels(labelSeries(rawLabels, series.length, locale));
      const hasLabels = labels.some((label) => label.length > 0);
      const Chart = viewType === "bar" ? BarChart : LineChart;
      body = (
        <div className="space-y-1.5">
          <Chart values={series} ariaLabel={chartAria} />
          {hasLabels ? (
            <div className="eh-caption flex justify-between gap-1 text-muted-foreground">
              {labels.map((label, index) => (
                <span key={index} className="min-w-0 truncate">
                  {label}
                </span>
              ))}
            </div>
          ) : null}
          {view.unit ? (
            <p className="eh-caption text-muted-foreground">{view.unit}</p>
          ) : null}
        </div>
      );
      break;
    }

    case "heatmap": {
      const rows = heatRows(value, locale);
      const cells = rows.flat();
      const numeric = cells.filter((cell) => cell.value !== null);
      if (numeric.length === 0) {
        body = missing;
        break;
      }
      const shown: HeatCell[][] = [];
      let count = 0;
      for (const row of rows) {
        const slice = row.slice(0, Math.max(HEATMAP_LIMIT - count, 0));
        if (slice.length > 0) shown.push(slice);
        count += slice.length;
        if (count >= HEATMAP_LIMIT) break;
      }
      const hiddenCount = cells.length - count;
      body = (
        <div className="space-y-1.5">
          <Heatmap rows={shown} ariaLabel={chartAria} />
          {hiddenCount > 0 ? (
            <p className="eh-caption text-muted-foreground">
              {t("moduleUi.widgets.moreItems", { count: hiddenCount })}
            </p>
          ) : null}
          {view.unit ? (
            <p className="eh-caption text-muted-foreground">{view.unit}</p>
          ) : null}
        </div>
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

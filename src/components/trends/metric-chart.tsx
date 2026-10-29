import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
  type DotItemDotProps,
} from "recharts";
import type { KeyboardEvent } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import type { TrendPoint, TrendSeries } from "@/lib/api/types";

interface ChartPoint extends TrendPoint {
  ts: number;
}

interface TrendDotProps extends DotItemDotProps {
  color?: string;
  unit?: string;
  metric?: string;
}

function TrendDot(props: TrendDotProps) {
  const { cx, cy, color, unit, metric } = props;
  const payload = props.payload as ChartPoint | undefined;
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const locale = intlLocale(i18n.language);
  if (cx === undefined || cy === undefined || !payload) return <g />;

  const openRecord = () => navigate(`/records/${payload.recordId}`);
  const onKeyDown = (event: KeyboardEvent<SVGCircleElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openRecord();
    }
  };

  return (
    <circle
      cx={cx}
      cy={cy}
      r={3.5}
      fill={color ?? "var(--eh-signal)"}
      stroke="var(--eh-surface)"
      strokeWidth={1.5}
      role="link"
      tabIndex={0}
      className="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      aria-label={t("trends.chart.pointAria", {
        date: formatDateTime(payload.t, locale),
        value: formatNumber(payload.value, locale, { maximumFractionDigits: 2 }),
        unit: unit ?? "",
        metric: metric ?? "",
      })}
      onClick={openRecord}
      onKeyDown={onKeyDown}
    />
  );
}

interface TrendTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ChartPoint }>;
  unit: string;
  metricLabel: string;
  locale: string;
}

function TrendTooltip({
  active,
  payload,
  unit,
  metricLabel,
  locale,
}: TrendTooltipProps) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-sm">
      <p className="eh-caption text-muted-foreground">
        {formatDateTime(point.t, locale)}
      </p>
      <p className="mt-1 flex items-baseline gap-1.5">
        <span className="eh-num text-sm font-medium">
          {formatNumber(point.value, locale, { maximumFractionDigits: 2 })}
        </span>
        <span className="text-muted-foreground">{unit}</span>
      </p>
      <p className="eh-caption mt-1 text-muted-foreground">{metricLabel}</p>
    </div>
  );
}

export function MetricChart({
  series,
  color,
}: {
  series: TrendSeries;
  color: string;
}) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const metricLabel = t(`measurements.codes.${series.metric}`, {
    defaultValue: series.label,
  });
  const data: ChartPoint[] = series.points.map((point) => ({
    ...point,
    ts: new Date(point.t).getTime(),
  }));
  const hasPoints = data.length > 0;

  // 自己量宽度：ResponsiveContainer 在 0 宽首帧会刷警告，图表在网格里也不稳定。
  const hostRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(0);
  useEffect(() => {
    const element = hostRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      setChartWidth(Math.round(entries[0]?.contentRect.width ?? 0));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const formatValue = (value: number | null) =>
    value === null
      ? "—"
      : formatNumber(value, locale, { maximumFractionDigits: 2 });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="eh-h3 flex flex-wrap items-baseline gap-2">
          {metricLabel}
          <span className="eh-caption font-normal text-muted-foreground">
            {series.unit}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {hasPoints ? (
          <figure
            role="group"
            aria-label={t("trends.chart.aria", { label: metricLabel })}
          >
            <div ref={hostRef} style={{ height: 220 }}>
              {chartWidth > 0 ? (
                <LineChart
                  width={chartWidth}
                  height={220}
                  data={data}
                  margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
                >
                  <CartesianGrid
                    stroke="var(--eh-grid-line)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="ts"
                    type="number"
                    scale="time"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(value: number) =>
                      new Intl.DateTimeFormat(locale, {
                        month: "numeric",
                        day: "numeric",
                      }).format(new Date(value))
                    }
                    stroke="var(--muted-foreground)"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={24}
                  />
                  <YAxis
                    domain={["auto", "auto"]}
                    tickFormatter={(value: number) =>
                      formatNumber(value, locale, {
                        maximumFractionDigits: 1,
                      })
                    }
                    stroke="var(--muted-foreground)"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--eh-grid-line)" }}
                    content={(props) => (
                      <TrendTooltip
                        active={props.active}
                        payload={
                          props.payload as
                            | ReadonlyArray<{ payload?: ChartPoint }>
                            | undefined
                        }
                        unit={series.unit}
                        metricLabel={metricLabel}
                        locale={locale}
                      />
                    )}
                  />
                  <Line
                    type="linear"
                    dataKey="value"
                    name={metricLabel}
                    stroke={color}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                    dot={(props) => (
                      <TrendDot
                        {...props}
                        color={color}
                        unit={series.unit}
                        metric={series.metric}
                      />
                    )}
                    activeDot={false}
                  />
                </LineChart>
              ) : null}
            </div>
          </figure>
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {t("trends.summaryEmpty")}
          </p>
        )}

        <p className="eh-caption text-muted-foreground">
          {series.summary.count > 0
            ? t("trends.summary", {
                count: series.summary.count,
                min: formatValue(series.summary.min),
                max: formatValue(series.summary.max),
                mean: formatValue(series.summary.mean),
              })
            : t("trends.summaryEmpty")}
        </p>

        {hasPoints ? (
          <details>
            <summary className="eh-caption cursor-pointer text-muted-foreground">
              {t("trends.chart.dataTable")}
            </summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-muted-foreground">
                    <th scope="col" className="py-1 pr-3 font-normal">
                      {t("trends.chart.date")}
                    </th>
                    <th scope="col" className="py-1 pr-3 font-normal">
                      {t("trends.chart.value")} ({series.unit})
                    </th>
                    <th scope="col" className="py-1 font-normal">
                      {t("trends.chart.record")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((point) => (
                    <tr key={`${point.recordId}-${point.t}`}>
                      <td className="py-1 pr-3">
                        {formatDateTime(point.t, locale)}
                      </td>
                      <td className="eh-num py-1 pr-3">
                        {formatValue(point.value)}
                      </td>
                      <td className="py-1">
                        <Link
                          to={`/records/${point.recordId}`}
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          {t("trends.chart.record")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

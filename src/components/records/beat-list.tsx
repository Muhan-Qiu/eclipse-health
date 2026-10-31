import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Beat } from "@/lib/api/types";
import { formatClock } from "@/lib/waveform";

const CLASS_ORDER = ["N", "SVEB", "VEB", "F"] as const;
const MAX_ROWS = 5_000;
const ROW_HEIGHT = 30;

export interface BeatListProps {
  beats: Beat[];
  fs: number;
  selectedIndex: number | null;
  onSelect: (beat: Beat | null) => void;
  loading?: boolean;
  className?: string;
  height?: number;
}

function labelVariant(label: string): "secondary" | "destructive" | "outline" {
  if (label === "N") return "secondary";
  if (label === "VEB" || label === "F") return "destructive";
  return "outline";
}

/**
 * 心搏列表（B3）：按类别/时间筛选、异常优先、点击定位、键盘上下切换。
 * 超过 5000 条时只渲染前 5000 条并提示，避免一次性铺 5 万 DOM。
 */
export function BeatList({
  beats,
  fs,
  selectedIndex,
  onSelect,
  loading = false,
  className,
  height = 264,
}: BeatListProps) {
  const { t } = useTranslation();
  const [classFilter, setClassFilter] = useState("all");
  const [abnormalOnly, setAbnormalOnly] = useState(false);
  const [sortMode, setSortMode] = useState<"abnormal" | "time">("abnormal");
  const [fromSec, setFromSec] = useState("");
  const [toSec, setToSec] = useState("");
  const [scrollTop, setScrollTop] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const limited = useMemo(
    () => (beats.length > MAX_ROWS ? beats.slice(0, MAX_ROWS) : beats),
    [beats],
  );

  const filtered = useMemo(() => {
    const from = fromSec.trim() === "" ? null : Number(fromSec);
    const to = toSec.trim() === "" ? null : Number(toSec);
    const rows = limited.filter((beat) => {
      const seconds = fs > 0 ? beat.rPeakSample / fs : 0;
      if (abnormalOnly && beat.label === "N") return false;
      if (classFilter !== "all" && beat.label !== classFilter) return false;
      if (from !== null && Number.isFinite(from) && seconds < from) return false;
      if (to !== null && Number.isFinite(to) && seconds > to) return false;
      return true;
    });
    if (sortMode === "time") {
      return [...rows].sort((a, b) => a.rPeakSample - b.rPeakSample);
    }
    return [...rows].sort((a, b) => {
      const aAbnormal = a.label === "N" ? 1 : 0;
      const bAbnormal = b.label === "N" ? 1 : 0;
      return aAbnormal - bAbnormal || a.rPeakSample - b.rPeakSample;
    });
  }, [limited, fs, abnormalOnly, classFilter, fromSec, toSec, sortMode]);

  const visibleCount = Math.ceil(height / ROW_HEIGHT);
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 4);
  const end = Math.min(filtered.length, start + visibleCount + 8);
  const visible = filtered.slice(start, end);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || selectedIndex === null) return;
    const position = filtered.findIndex((beat) => beat.index === selectedIndex);
    if (position < 0) return;
    const top = position * ROW_HEIGHT;
    if (top < container.scrollTop) {
      container.scrollTop = top;
    } else if (top + ROW_HEIGHT > container.scrollTop + height) {
      container.scrollTop = top + ROW_HEIGHT - height;
    }
  }, [selectedIndex, filtered, height]);

  const moveSelection = (direction: 1 | -1) => {
    if (!filtered.length) return;
    const current = filtered.findIndex((beat) => beat.index === selectedIndex);
    const next =
      current < 0
        ? direction > 0
          ? 0
          : filtered.length - 1
        : Math.max(0, Math.min(filtered.length - 1, current + direction));
    onSelect(filtered[next]);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      if (filtered.length) onSelect(filtered[0]);
    } else if (event.key === "End") {
      event.preventDefault();
      if (filtered.length) onSelect(filtered[filtered.length - 1]);
    }
  };

  const truncated = beats.length > MAX_ROWS;

  return (
    <section
      className={cn("rounded-lg border border-border bg-surface", className)}
      aria-label={t("beatList.title")}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-2.5 py-2">
        <h4 className="eh-caption text-foreground">{t("beatList.title")}</h4>
        <span className="eh-caption eh-num text-muted-foreground">
          {t("beatList.count", { shown: filtered.length, total: beats.length })}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
            {t("beatList.classFilter")}
            <select
              value={classFilter}
              onChange={(event) => setClassFilter(event.target.value)}
              className="h-6 rounded-md border border-border bg-surface px-1 text-[11px] text-foreground"
              aria-label={t("beatList.classFilter")}
            >
              <option value="all">{t("beatList.allClasses")}</option>
              {CLASS_ORDER.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant={abnormalOnly ? "secondary" : "ghost"}
            size="xs"
            aria-pressed={abnormalOnly}
            onClick={() => setAbnormalOnly((value) => !value)}
          >
            {t("beatList.abnormalOnly")}
          </Button>
          <Button
            variant="ghost"
            size="xs"
            onClick={() =>
              setSortMode((mode) => (mode === "abnormal" ? "time" : "abnormal"))
            }
            title={t("beatList.sort")}
          >
            {sortMode === "abnormal"
              ? t("beatList.sortAbnormal")
              : t("beatList.sortTime")}
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-1.5 px-2.5 py-1.5 text-[11px] text-muted-foreground">
        <span>{t("beatList.timeRange")}</span>
        <input
          type="number"
          inputMode="decimal"
          value={fromSec}
          onChange={(event) => setFromSec(event.target.value)}
          placeholder={t("beatList.timeFrom")}
          aria-label={t("beatList.timeFrom")}
          className="h-6 w-16 rounded-md border border-border bg-surface px-1.5 text-[11px] text-foreground"
        />
        <span>–</span>
        <input
          type="number"
          inputMode="decimal"
          value={toSec}
          onChange={(event) => setToSec(event.target.value)}
          placeholder={t("beatList.timeTo")}
          aria-label={t("beatList.timeTo")}
          className="h-6 w-16 rounded-md border border-border bg-surface px-1.5 text-[11px] text-foreground"
        />
        {truncated ? (
          <span className="ml-auto flex items-center gap-1 text-warning">
            <AlertTriangle className="size-3" aria-hidden="true" />
            {t("beatList.truncated", { limit: MAX_ROWS, total: beats.length })}
          </span>
        ) : null}
      </div>

      <div
        className="grid grid-cols-[36px_64px_minmax(64px,1fr)_64px_64px] items-center gap-1 border-y border-border bg-subtle/60 px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground"
        aria-hidden="true"
      >
        <span>{t("beatList.columns.index")}</span>
        <span>{t("beatList.columns.time")}</span>
        <span>{t("beatList.columns.label")}</span>
        <span className="text-right">{t("beatList.columns.confidence")}</span>
        <span className="text-right">{t("beatList.columns.rr")}</span>
      </div>

      <div
        ref={scrollRef}
        role="listbox"
        tabIndex={0}
        aria-label={t("beatList.aria", { count: filtered.length })}
        aria-activedescendant={
          selectedIndex === null ? undefined : `beat-row-${selectedIndex}`
        }
        onKeyDown={onKeyDown}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        className="relative overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        style={{ height }}
      >
        {loading ? (
          <p className="p-3 text-xs text-muted-foreground">{t("beatList.loading")}</p>
        ) : filtered.length === 0 ? (
          <p className="p-3 text-xs text-muted-foreground">
            {beats.length === 0
              ? t("beatList.emptyNoAnalysis")
              : t("beatList.empty")}
          </p>
        ) : (
          <div style={{ height: filtered.length * ROW_HEIGHT }} className="relative">
            {visible.map((beat, offset) => {
              const position = start + offset;
              const selected = beat.index === selectedIndex;
              const abnormal = beat.label !== "N";
              return (
                <button
                  type="button"
                  key={`${beat.index}-${beat.rPeakSample}`}
                  id={`beat-row-${beat.index}`}
                  role="option"
                  aria-selected={selected}
                  aria-label={t("beatList.select", { index: beat.index + 1 })}
                  onClick={() => onSelect(beat)}
                  className={cn(
                    "absolute inset-x-0 grid grid-cols-[36px_64px_minmax(64px,1fr)_64px_64px] items-center gap-1 border-l-2 px-2 text-left text-[11px] eh-num tabular-nums transition-colors duration-[120ms]",
                    selected
                      ? "border-l-[var(--eh-accent)] bg-accent-soft"
                      : "border-l-transparent hover:bg-subtle",
                  )}
                  style={{ top: position * ROW_HEIGHT, height: ROW_HEIGHT }}
                >
                  <span className="text-muted-foreground">{beat.index + 1}</span>
                  <span>{formatClock(fs > 0 ? beat.rPeakSample / fs : 0)}</span>
                  <span className="flex items-center gap-1">
                    <Badge variant={labelVariant(beat.label)} className="h-4 px-1 text-[10px]">
                      {beat.label}
                    </Badge>
                    {selected ? (
                      <span className="text-[9px] text-muted-foreground">
                        {t("beatList.current")}
                      </span>
                    ) : null}
                  </span>
                  <span
                    className={cn(
                      "text-right",
                      abnormal ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {(beat.confidence * 100).toFixed(1)}%
                  </span>
                  <span className="text-right text-muted-foreground">
                    {beat.rrPrevMs === null ? "—" : `${Math.round(beat.rrPrevMs)} ms`}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

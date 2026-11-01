import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useQueries } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Download,
  LayoutGrid,
  Loader2,
  Maximize2,
  RotateCcw,
  Waves,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { queryKeys, useRecordSignals } from "@/lib/api/queries";
import type { AnalysisResult, Beat, SignalData } from "@/lib/api/types";
import { clampView, formatClock, formatSeconds, buildEnvelope } from "@/lib/waveform";
import { LeadStrip } from "@/features/waveform/lead-strip";
import { OverviewStrip } from "@/features/waveform/overview-strip";
import { exportWaveformPng, type PngLead } from "@/features/waveform/export-png";
import { waveColors } from "@/features/waveform/colors";

const GRID_CELL_HEIGHT = 76;

export interface WaveformViewerHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  pan: (fraction: number) => void;
  reset: () => void;
  focusBeat: (index: number) => void;
  focusRange: (startSec: number, endSec: number) => void;
  exportPng: (mode: "view" | "full") => Promise<void>;
  getView: () => [number, number];
}

export interface WaveformViewerProps {
  recordId: string;
  leads: string[];
  analysis?: AnalysisResult | null;
  selectedBeatIndex?: number | null;
  onBeatSelect?: (beat: Beat | null) => void;
  height?: number;
  compact?: boolean;
  className?: string;
  /** 导出 PNG 时写入的记录时间；由父组件按当前语言格式化。 */
  recordDate?: string;
  defaultLayout?: "single" | "grid";
}

function primaryOf(leads: string[], fallback: string[] = []): string {
  const all = leads.length ? leads : fallback;
  return all.find((lead) => lead.toUpperCase() === "MLII") ?? all[0] ?? "";
}

/**
 * 记录详情波形：单导联主视图、12 导联网格、节律条与 PNG 导出。
 *
 * 单导联是分析口径（Cardia 2.0 单导联模型）；多导联记录只做同步展示，
 * 所有导联共享同一个时间窗，切换布局不会改变分析结果。
 */
export const WaveformViewer = forwardRef<WaveformViewerHandle, WaveformViewerProps>(
  function WaveformViewer(
    {
      recordId,
      leads,
      analysis = null,
      selectedBeatIndex = null,
      onBeatSelect,
      height = 300,
      compact = false,
      className,
      recordDate,
      defaultLayout = "single",
    },
    ref,
  ) {
    const { t } = useTranslation();
    const signalsQuery = useRecordSignals(recordId);
    const availableLeads = useMemo(() => {
      const fromMeta = (signalsQuery.data ?? []).map((signal) => signal.lead);
      return fromMeta.length ? fromMeta : leads;
    }, [leads, signalsQuery.data]);
    const primaryLead = useMemo(() => primaryOf(availableLeads), [availableLeads]);

    const [lead, setLead] = useState(primaryLead);
    const [layout, setLayout] = useState<"single" | "grid">(
      compact ? "single" : defaultLayout,
    );

    useEffect(() => {
      if (!availableLeads.length) return;
      if (!availableLeads.includes(lead)) setLead(primaryLead);
    }, [availableLeads, lead, primaryLead]);

    useEffect(() => {
      if (availableLeads.length <= 1) setLayout("single");
    }, [availableLeads.length]);

    const leadQueries = useQueries({
      queries: availableLeads.map((name) => ({
        queryKey: queryKeys.signal(recordId, name),
        queryFn: () => api.records.signal(recordId, name),
        enabled: layout === "grid" || name === lead || name === primaryLead,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: 10 * 60_000,
      })),
    });

    const dataFor = useCallback(
      (name: string): SignalData | undefined => {
        const index = availableLeads.indexOf(name);
        return index >= 0 ? leadQueries[index]?.data : undefined;
      },
      [availableLeads, leadQueries],
    );

    const primarySignal = dataFor(primaryLead);
    const currentSignal = dataFor(lead);
    const duration =
      primarySignal && primarySignal.fs > 0
        ? primarySignal.sampleCount / primarySignal.fs
        : currentSignal && currentSignal.fs > 0
          ? currentSignal.sampleCount / currentSignal.fs
          : 0;
    const fs = currentSignal?.fs ?? primarySignal?.fs ?? 0;
    const primaryIndex = Math.max(0, availableLeads.indexOf(primaryLead));
    const primaryQuery = leadQueries[primaryIndex];

    const [view, setView] = useState<[number, number]>([0, 0]);
    const viewRef = useRef(view);
    viewRef.current = view;
    const rafRef = useRef<number | null>(null);
    const pendingRef = useRef<[number, number] | null>(null);

    useEffect(() => {
      if (duration <= 0) return;
      // 长记录默认展示前 12 秒；整段 30 分钟压成一条实心带没有复查价值。
      setView([0, Math.min(duration, 12)]);
    }, [recordId, duration]);

    useEffect(
      () => () => {
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      },
      [],
    );

    const applyView = useCallback(
      (nextStart: number, nextEnd: number) => {
        if (!duration) return;
        const next = clampView(nextStart, nextEnd, duration);
        viewRef.current = next;
        pendingRef.current = next;
        if (rafRef.current === null) {
          rafRef.current = requestAnimationFrame(() => {
            rafRef.current = null;
            if (pendingRef.current) setView(pendingRef.current);
          });
        }
      },
      [duration],
    );

    const zoomAt = useCallback(
      (factor: number, ratio = 0.5) => {
        const [start, end] = viewRef.current;
        const span = end - start;
        const nextSpan = Math.min(duration, Math.max(0.2, span * factor));
        const cursor = start + span * ratio;
        applyView(cursor - nextSpan * ratio, cursor + nextSpan * (1 - ratio));
      },
      [applyView, duration],
    );

    const pan = useCallback(
      (fraction: number) => {
        const [start, end] = viewRef.current;
        const span = end - start;
        applyView(start + span * fraction, end + span * fraction);
      },
      [applyView],
    );

    const resetView = useCallback(() => {
      applyView(0, Math.min(duration, 12));
    }, [applyView, duration]);

    const focusBeat = useCallback(
      (index: number) => {
        const beat = analysis?.beats[index];
        if (!beat || fs <= 0) return;
        const center = beat.rPeakSample / fs;
        const [start, end] = viewRef.current;
        const span = Math.min(6, Math.max(2, end - start));
        applyView(center - span / 2, center + span / 2);
      },
      [analysis, fs, applyView],
    );

    const focusRange = useCallback(
      (startSec: number, endSec: number) => {
        if (!duration) return;
        const nextSpan = Math.min(
          duration,
          Math.max(0.5, (endSec - startSec) * 1.2),
        );
        const center = (startSec + endSec) / 2;
        applyView(center - nextSpan / 2, center + nextSpan / 2);
      },
      [applyView, duration],
    );

    const envelope = useMemo(
      () =>
        primarySignal && primarySignal.fs > 0
          ? buildEnvelope(primarySignal.samples, primarySignal.fs)
          : null,
      [primarySignal],
    );

    const [exporting, setExporting] = useState(false);

    const exportPng = useCallback(
      async (mode: "view" | "full") => {
        const names = layout === "grid" ? availableLeads : [lead];
        const pngLeads: PngLead[] = names.flatMap((name) => {
          const signal = dataFor(name);
          if (!signal) return [];
          const meta = signalsQuery.data?.find((item) => item.lead === name);
          return [
            {
              lead: name,
              unit: meta?.unit ?? signal.unit ?? "mV",
              samples: signal.samples,
              fs: signal.fs,
            },
          ];
        });
        if (!pngLeads.length) {
          toast.error(t("waveform.controls.exportFailed"));
          return;
        }
        const [start, end] =
          mode === "full" ? [0, duration] : viewRef.current;
        const colors = waveColors();
        const stamp =
          (recordDate ?? "").replace(/[^\d]/g, "").slice(0, 12) || "record";
        const leadPart =
          layout === "grid"
            ? `${pngLeads.length}-leads`
            : lead.replace(/[^\w.-]+/g, "_");
        const joined =
          pngLeads
            .slice(0, 3)
            .map((item) => item.lead)
            .join(", ") +
          (pngLeads.length > 3 ? ` +${pngLeads.length - 3}` : "");
        setExporting(true);
        try {
          await exportWaveformPng({
            leads: pngLeads,
            view: [start, end],
            duration,
            layout,
            recordDate: recordDate ?? "",
            beats: analysis?.beats ?? [],
            selectedBeatIndex,
            quality: analysis?.quality ?? null,
            labels: {
              title: t("waveform.png.title"),
              date: t("waveform.png.date", { date: recordDate ?? "—" }),
              meta: t("waveform.png.meta", {
                lead: joined,
                fs: (fs || pngLeads[0]?.fs || 0).toFixed(0),
                start: formatClock(start),
                end: formatClock(end),
              }),
              watermark: t("waveform.png.watermark"),
              duration: t("waveform.png.duration", {
                duration: formatSeconds(duration),
              }),
              layout: t(`waveform.png.layouts.${layout}`),
            },
            colors,
            filename: `ecg-${leadPart}-${stamp}.png`,
          });
          toast.success(t("waveform.controls.exported"));
        } catch (error) {
          toast.error(t("waveform.controls.exportFailed"), {
            description: error instanceof Error ? error.message : undefined,
          });
        } finally {
          setExporting(false);
        }
      },
      [
        analysis,
        availableLeads,
        dataFor,
        duration,
        fs,
        layout,
        lead,
        recordDate,
        selectedBeatIndex,
        signalsQuery.data,
        t,
      ],
    );

    useImperativeHandle(
      ref,
      () => ({
        zoomIn: () => zoomAt(0.8),
        zoomOut: () => zoomAt(1.25),
        pan,
        reset: resetView,
        focusBeat,
        focusRange,
        exportPng,
        getView: () => viewRef.current,
      }),
      [zoomAt, pan, resetView, focusBeat, focusRange, exportPng],
    );

    if (signalsQuery.isLoading) {
      return <Skeleton className={cn("w-full rounded-lg", className)} style={{ height }} />;
    }

    if (signalsQuery.isError || !availableLeads.length) {
      return (
        <div
          className={cn(
            "flex items-center justify-center rounded-lg border border-dashed border-border px-4 text-center",
            className,
          )}
          style={{ height }}
        >
          <p className="eh-small text-muted-foreground">
            {signalsQuery.isError ? t("waveform.loadError") : t("waveform.empty")}
          </p>
        </div>
      );
    }

    if (!currentSignal && (layout === "single" || !primarySignal)) {
      if (primaryQuery?.isError) {
        return (
          <div
            className={cn(
              "flex items-center justify-center rounded-lg border border-dashed border-border px-4 text-center",
              className,
            )}
            style={{ height }}
          >
            <p className="eh-small text-muted-foreground">{t("waveform.loadError")}</p>
          </div>
        );
      }
      return <Skeleton className={cn("w-full rounded-lg", className)} style={{ height }} />;
    }

    const beatCount = analysis?.beats.length ?? 0;
    const gridLeadCount = availableLeads.length;
    const loadedGridLeads = availableLeads.filter((name) => dataFor(name)).length;

    const controls = !compact ? (
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          {layout === "single" ? (
            <div
              className="flex flex-wrap items-center gap-1"
              role="group"
              aria-label={t("waveform.lead")}
            >
              {availableLeads.map((item) => (
                <Button
                  key={item}
                  variant={item === lead ? "secondary" : "ghost"}
                  size="xs"
                  aria-pressed={item === lead}
                  onClick={() => setLead(item)}
                >
                  {item}
                </Button>
              ))}
            </div>
          ) : (
            <span className="eh-caption text-muted-foreground">
              {t("waveform.controls.grid")} ·{" "}
              {loadedGridLeads < gridLeadCount
                ? t("waveform.multiLead.partial", {
                    loaded: loadedGridLeads,
                    total: gridLeadCount,
                  })
                : t("waveform.multiLead.count", { count: gridLeadCount })}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {availableLeads.length > 1 ? (
            <div className="flex items-center gap-0.5" role="group" aria-label={t("waveform.controls.layout")}>
              <Button
                variant={layout === "single" ? "secondary" : "ghost"}
                size="icon-xs"
                aria-label={t("waveform.controls.single")}
                aria-pressed={layout === "single"}
                onClick={() => setLayout("single")}
              >
                <Waves aria-hidden="true" />
              </Button>
              <Button
                variant={layout === "grid" ? "secondary" : "ghost"}
                size="icon-xs"
                aria-label={t("waveform.controls.grid")}
                aria-pressed={layout === "grid"}
                onClick={() => setLayout("grid")}
              >
                <LayoutGrid aria-hidden="true" />
              </Button>
            </div>
          ) : null}
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("waveform.zoomIn")}
            onClick={() => zoomAt(0.8)}
          >
            <ZoomIn aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("waveform.zoomOut")}
            onClick={() => zoomAt(1.25)}
          >
            <ZoomOut aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("waveform.reset")}
            onClick={resetView}
          >
            <RotateCcw aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("waveform.showFull")}
            onClick={() => applyView(0, duration)}
            disabled={duration <= 12}
          >
            <Maximize2 aria-hidden="true" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("waveform.controls.export")}
                disabled={exporting}
              >
                {exporting ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <Download aria-hidden="true" />
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void exportPng("view")}>
                {t("waveform.controls.exportView")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void exportPng("full")}>
                {t("waveform.controls.exportFull")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    ) : null;

    return (
      <div className={className}>
        {controls}

        {availableLeads.length > 1 && !compact ? (
          <p className="eh-caption mb-2 text-muted-foreground">
            {t("waveform.multiLead.note", {
              lead: primaryLead,
              count: availableLeads.length - 1,
            })}
          </p>
        ) : null}

        {!compact && envelope && duration > 0 ? (
          <OverviewStrip
            envelope={envelope}
            duration={duration}
            view={view}
            quality={analysis?.quality ?? null}
            onViewChange={([start, end]) => applyView(start, end)}
            height={40}
            className="mb-2"
            hint={`${t("waveform.overview.label")} · ${t("waveform.overview.hint")}`}
            ariaLabel={t("waveform.overview.aria", {
              duration: formatSeconds(duration),
              start: formatSeconds(view[0]),
              end: formatSeconds(view[1]),
            })}
          />
        ) : null}

        {layout === "grid" && availableLeads.length > 1 ? (
          <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
            {availableLeads.map((name) => {
              const signal = dataFor(name);
              const meta = signalsQuery.data?.find((item) => item.lead === name);
              if (!signal) {
                return (
                  <div
                    key={name}
                    className="flex items-center justify-center rounded-md border border-dashed border-border text-[11px] text-muted-foreground"
                    style={{ height: GRID_CELL_HEIGHT + 20 }}
                  >
                    {t("waveform.multiLead.loading")}
                  </div>
                );
              }
              return (
                <LeadStrip
                  key={name}
                  samples={signal.samples}
                  fs={signal.fs}
                  lead={name}
                  unit={meta?.unit ?? signal.unit ?? "mV"}
                  view={view}
                  duration={duration}
                  height={GRID_CELL_HEIGHT}
                  showHeader
                  showTimeAxis
                  showScale
                  isPrimary={name === primaryLead}
                  interactive
                  analysis={analysis}
                  selectedBeatIndex={selectedBeatIndex}
                  onBeatSelect={onBeatSelect}
                  onViewChange={([start, end]) => applyView(start, end)}
                />
              );
            })}
          </div>
        ) : currentSignal ? (
          <LeadStrip
            samples={currentSignal.samples}
            fs={currentSignal.fs}
            lead={lead}
            unit={
              signalsQuery.data?.find((item) => item.lead === lead)?.unit ??
              currentSignal.unit ??
              "mV"
            }
            view={view}
            duration={duration}
            height={height}
            showTimeAxis
            showScale
            interactive={!compact}
            analysis={analysis}
            selectedBeatIndex={selectedBeatIndex}
            onBeatSelect={onBeatSelect}
            onViewChange={([start, end]) => applyView(start, end)}
            ariaLabel={t("waveform.ariaLabel", {
              lead,
              duration: formatSeconds(duration),
              fs: (currentSignal.fs || 0).toFixed(0),
              beats: beatCount,
            })}
          />
        ) : (
          <Skeleton className="w-full rounded-lg" style={{ height }} />
        )}

        {!compact ? (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <p className="eh-caption text-muted-foreground">
              {t("shortcuts.hint")}
            </p>
            <p className="eh-caption text-muted-foreground">
              {t("waveform.summary", {
                duration: formatSeconds(duration),
                fs: fs.toFixed(0),
                beats: beatCount,
              })}
            </p>
          </div>
        ) : null}
      </div>
    );
  },
);

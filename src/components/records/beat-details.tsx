import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Beat } from "@/lib/api/types";
import { formatClock } from "@/lib/waveform";
import { BeatProbabilityBars } from "./class-ratio-bars";

export function BeatDetails({
  beat,
  fs,
  onClose,
}: {
  beat: Beat;
  fs: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const abnormal = beat.label !== "N";
  return (
    <div className="rounded-lg border border-border bg-subtle/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={abnormal ? "destructive" : "secondary"}>
          {t(`analysis.classes.${beat.label}`, { defaultValue: beat.label })}
        </Badge>
        <span className="eh-caption text-muted-foreground">
          {t("beat.index", { index: beat.index + 1 })}
        </span>
        <span className="eh-caption text-muted-foreground">
          {t("beat.rTime", { time: formatClock(beat.rPeakSample / fs) })}
        </span>
        {beat.rrPrevMs !== null ? (
          <span className="eh-caption text-muted-foreground">
            {t("beat.rrPrev", { ms: Math.round(beat.rrPrevMs) })}
          </span>
        ) : null}
        <span className="eh-caption ml-auto text-muted-foreground">
          {t("beat.confidence", {
            value: `${(beat.confidence * 100).toFixed(1)}%`,
          })}
        </span>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={onClose}
          aria-label={t("beat.close")}
        >
          <X aria-hidden="true" />
        </Button>
      </div>
      <div className="mt-3">
        <BeatProbabilityBars beat={beat} />
      </div>
      <p className="eh-caption mt-2 text-muted-foreground">
        {t("beat.note")}
      </p>
    </div>
  );
}

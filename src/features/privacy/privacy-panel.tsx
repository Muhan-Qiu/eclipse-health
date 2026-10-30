import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  PURGE_CONFIRM_TOKEN,
  fetchStorage,
  purgeAll,
  type StorageInfo,
} from "./api";

interface PrivacyPanelProps {
  className?: string;
  refreshSignal?: number;
  onPurged?: () => void;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function PrivacyPanel({
  className,
  refreshSignal = 0,
  onPurged,
}: PrivacyPanelProps) {
  const { t } = useTranslation();
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [confirmWord, setConfirmWord] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [purging, setPurging] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchStorage()
      .then((info) => {
        if (!active) return;
        setStorage(info);
        setError(false);
      })
      .catch(() => {
        if (!active) return;
        setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSignal, version]);

  async function handlePurge() {
    setPurging(true);
    try {
      const result = await purgeAll();
      toast.success(
        t("privacy.clearDone", {
          records: result.deleted.records,
          signals: result.deleted.signals,
        }),
      );
      setConfirmWord("");
      setVersion((value) => value + 1);
      onPurged?.();
    } catch (err) {
      toast.error(t("privacy.clearFailed"), {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setPurging(false);
    }
  }

  const canPurge = confirmWord.trim() === PURGE_CONFIRM_TOKEN;

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("privacy.title")}</CardTitle>
        <CardDescription>{t("privacy.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="eh-caption text-muted-foreground">
              {t("privacy.storageTitle")}
            </h3>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={t("privacy.refresh")}
              disabled={loading}
              onClick={() => setVersion((value) => value + 1)}
            >
              <RefreshCw aria-hidden="true" />
            </Button>
          </div>

          {error ? (
            <p className="text-sm text-destructive">{t("privacy.storageError")}</p>
          ) : storage ? (
            <div className="space-y-3 text-sm">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {(
                  [
                    ["records", storage.counts.records],
                    ["signals", storage.counts.signals],
                    ["analyses", storage.counts.analyses],
                    ["reports", storage.counts.reports],
                  ] as const
                ).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-2">
                    <dt className="text-muted-foreground">{t(`privacy.${key}`)}</dt>
                    <dd className="eh-num">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="eh-caption text-muted-foreground">
                {t("privacy.size", {
                  signals: formatBytes(storage.bytes.signals),
                  reports: formatBytes(storage.bytes.reports),
                  database: formatBytes(storage.bytes.database),
                })}
              </p>
              <div>
                <p className="eh-caption text-muted-foreground">
                  {t("privacy.dataDir")}
                </p>
                <code className="mt-1 block break-all rounded-md bg-muted px-2 py-1 text-xs">
                  {storage.dataDir}
                </code>
              </div>
              <p className="eh-caption text-muted-foreground">
                {t("privacy.localOnly")}
              </p>
            </div>
          ) : (
            <div className="h-16 animate-pulse rounded-lg bg-muted" />
          )}
        </section>

        <section className="border-t border-border pt-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">{t("privacy.telemetryTitle")}</p>
              <p className="eh-caption text-muted-foreground">
                {t("privacy.telemetryDesc")}
              </p>
            </div>
            <Switch checked={false} disabled aria-label={t("privacy.telemetryTitle")} />
          </div>
        </section>

        <section className="space-y-3 border-t border-border pt-4">
          <div>
            <p className="text-sm font-medium">{t("privacy.clearTitle")}</p>
            <p className="eh-caption text-muted-foreground">
              {t("privacy.clearDesc")}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-40 flex-1">
              <Label htmlFor="privacy-confirm" className="eh-caption">
                {t("privacy.clearHint", { word: PURGE_CONFIRM_TOKEN })}
              </Label>
              <Input
                id="privacy-confirm"
                value={confirmWord}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => setConfirmWord(event.target.value)}
              />
            </div>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={!canPurge || purging}
              onClick={() => setDialogOpen(true)}
            >
              <Trash2 aria-hidden="true" />
              {purging ? t("privacy.clearing") : t("privacy.clearAction")}
            </Button>
          </div>
        </section>
      </CardContent>

      <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t("privacy.clearConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("privacy.clearConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={purging}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={purging}
              onClick={() => void handlePurge()}
            >
              <Trash2 aria-hidden="true" />
              {purging ? t("privacy.clearing") : t("privacy.clearAction")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

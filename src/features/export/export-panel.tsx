import { useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { Archive, Download, FileJson, Table2, Upload } from "lucide-react";
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
import {
  downloadBackup,
  restoreBackup,
  saveBlob,
  type BackupFormat,
  type RestoreResult,
} from "./api";

const FORMATS: {
  format: BackupFormat;
  icon: typeof Archive;
  titleKey: string;
  descKey: string;
}[] = [
  { format: "zip", icon: Archive, titleKey: "export.zip", descKey: "export.zipDesc" },
  {
    format: "json",
    icon: FileJson,
    titleKey: "export.json",
    descKey: "export.jsonDesc",
  },
  { format: "csv", icon: Table2, titleKey: "export.csv", descKey: "export.csvDesc" },
];

interface ExportPanelProps {
  className?: string;
  onDataChanged?: () => void;
}

export function ExportPanel({ className, onDataChanged }: ExportPanelProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<BackupFormat | "restore" | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [result, setResult] = useState<RestoreResult | null>(null);

  async function handleDownload(format: BackupFormat) {
    setBusy(format);
    try {
      saveBlob(await downloadBackup(format));
      toast.success(t("export.downloadDone"));
    } catch (error) {
      toast.error(t("export.downloadFailed"), {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setBusy(null);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error(t("export.invalidFile"));
      return;
    }
    setPendingFile(file);
    setDialogOpen(true);
    // 允许重复选择同一个文件
    event.target.value = "";
  }

  async function handleRestore() {
    if (!pendingFile) return;
    setBusy("restore");
    try {
      const body = await restoreBackup(pendingFile);
      setResult(body);
      onDataChanged?.();
      toast.success(t("export.restoreDone"), {
        description: t("export.restoreResult", {
          records: body.imported.records,
          signals: body.imported.signals,
          analyses: body.imported.analyses,
          measurements: body.imported.measurements,
          reports: body.imported.reports,
        }),
      });
    } catch (error) {
      toast.error(t("export.restoreFailed"), {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setBusy(null);
      setPendingFile(null);
    }
  }

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("export.title")}</CardTitle>
        <CardDescription>{t("export.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section>
          <h3 className="eh-caption mb-2 text-muted-foreground">
            {t("export.downloadTitle")}
          </h3>
          <div className="grid gap-2 sm:grid-cols-3">
            {FORMATS.map(({ format, icon: Icon, titleKey, descKey }) => (
              <button
                key={format}
                type="button"
                disabled={busy !== null}
                onClick={() => void handleDownload(format)}
                className={cn(
                  "rounded-xl border border-border p-3 text-left transition-colors",
                  "hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60",
                )}
              >
                <span className="flex items-center gap-2 text-sm font-medium">
                  <Icon className="size-4" aria-hidden="true" />
                  {t(titleKey)}
                </span>
                <span className="eh-caption mt-1 block text-muted-foreground">
                  {t(descKey)}
                </span>
              </button>
            ))}
          </div>
          <p className="eh-caption mt-2 text-muted-foreground">
            {t("export.localOnly")}
          </p>
        </section>

        <section className="border-t border-border pt-4">
          <h3 className="eh-caption mb-2 text-muted-foreground">
            {t("export.restoreTitle")}
          </h3>
          <p className="mb-3 text-sm text-muted-foreground">
            {t("export.restoreDesc")}
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            className="sr-only"
            onChange={handleFileChange}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy !== null}
            onClick={() => inputRef.current?.click()}
          >
            <Upload aria-hidden="true" />
            {busy === "restore" ? t("export.restoring") : t("export.chooseFile")}
          </Button>
          {result ? (
            <div className="mt-4 space-y-1 rounded-lg border border-border bg-muted/40 p-3 text-sm">
              <p>
                {t("export.restoreResult", {
                  records: result.imported.records,
                  signals: result.imported.signals,
                  analyses: result.imported.analyses,
                  measurements: result.imported.measurements,
                  reports: result.imported.reports,
                })}
              </p>
              <p className="eh-caption text-muted-foreground">
                {t("export.autoBackup", { name: result.autoBackup })}
              </p>
            </div>
          ) : null}
        </section>
      </CardContent>

      <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t("export.restoreConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("export.restoreConfirmDesc", {
                name: pendingFile?.name ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy === "restore"}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={busy === "restore"}
              onClick={() => void handleRestore()}
            >
              <Download aria-hidden="true" />
              {busy === "restore" ? t("export.restoring") : t("export.restore")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

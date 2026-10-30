import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Trash2 } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ModuleSummary } from "./types";

interface UninstallDialogProps {
  open: boolean;
  module: ModuleSummary | null;
  busy: boolean;
  onClose: () => void;
  onConfirm: (keepData: boolean) => void;
}

export function UninstallDialog({
  open,
  module,
  busy,
  onClose,
  onConfirm,
}: UninstallDialogProps) {
  const { t } = useTranslation();
  const [keepData, setKeepData] = useState(true);

  useEffect(() => {
    if (open) setKeepData(true);
  }, [open]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md" showCloseButton={!busy}>
        <DialogHeader>
          <DialogTitle>{t("moduleUi.uninstall.title", { name: module?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("moduleUi.uninstall.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <button
            type="button"
            aria-pressed={keepData}
            disabled={busy}
            onClick={() => setKeepData(true)}
            className={cn(
              "w-full rounded-lg border p-3 text-left transition-colors",
              keepData
                ? "border-primary bg-accent-soft"
                : "border-border hover:bg-accent",
            )}
          >
            <span className="block text-sm font-medium">
              {t("moduleUi.uninstall.keepData")}
            </span>
            <span className="eh-caption block text-muted-foreground">
              {t("moduleUi.uninstall.keepDataDesc")}
            </span>
          </button>
          <button
            type="button"
            aria-pressed={!keepData}
            disabled={busy}
            onClick={() => setKeepData(false)}
            className={cn(
              "w-full rounded-lg border p-3 text-left transition-colors",
              !keepData
                ? "border-destructive bg-destructive/5"
                : "border-border hover:bg-accent",
            )}
          >
            <span className="block text-sm font-medium">
              {t("moduleUi.uninstall.deleteData")}
            </span>
            <span className="eh-caption block text-muted-foreground">
              {t("moduleUi.uninstall.deleteDataDesc")}
            </span>
          </button>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={busy}
            onClick={() => onConfirm(keepData)}
          >
            {busy ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 aria-hidden="true" />
            )}
            {busy ? t("moduleUi.uninstall.working") : t("moduleUi.uninstall.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

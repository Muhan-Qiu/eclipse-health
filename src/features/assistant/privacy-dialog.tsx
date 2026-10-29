import { useTranslation } from "react-i18next";
import { LockKeyhole, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AssistantProvider } from "./types";

export interface PrivacyDialogProps {
  open: boolean;
  provider: AssistantProvider | null;
  includeNotes: boolean;
  hasLocalProvider: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onUseLocal: () => void;
}

export function PrivacyDialog({
  open,
  provider,
  includeNotes,
  hasLocalProvider,
  onCancel,
  onConfirm,
  onUseLocal,
}: PrivacyDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={(next) => (!next ? onCancel() : undefined)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="size-4" aria-hidden="true" />
            {t("assistant.privacy.title")}
          </DialogTitle>
          <DialogDescription>
            {t("assistant.privacy.description", {
              provider: provider?.label ?? provider?.kind ?? "—",
            })}
          </DialogDescription>
        </DialogHeader>

        <ol className="space-y-2 text-sm">
          <li className="flex gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
            {t("assistant.transparency.sentTitle")}：record.* / analysis.* /
            measurement.*
          </li>
          <li className="flex gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
            {t("assistant.privacy.waveformNote")}
          </li>
          <li className="flex gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
            {includeNotes ? t("assistant.transparency.notesIncluded") : t("assistant.privacy.notesNote")}
          </li>
        </ol>

        <p className="eh-caption rounded-lg bg-muted/40 p-2.5 text-muted-foreground">
          {t("assistant.privacy.providerNote")}
        </p>

        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={onCancel}>
              {t("assistant.privacy.cancel")}
            </Button>
            {hasLocalProvider ? (
              <Button variant="ghost" onClick={onUseLocal}>
                <LockKeyhole data-icon="inline-start" />
                {t("assistant.privacy.localOnly")}
              </Button>
            ) : null}
          </div>
          <Button onClick={onConfirm}>{t("assistant.privacy.confirm")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

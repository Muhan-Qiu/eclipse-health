import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileWarning, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { downloadDiagnosticsBundle, saveBlob } from "./api";

interface DiagnosticsPanelProps {
  className?: string;
}

export function DiagnosticsPanel({ className }: DiagnosticsPanelProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  async function handleDownload() {
    setBusy(true);
    try {
      saveBlob(await downloadDiagnosticsBundle());
      toast.success(t("diagnostics.done"));
    } catch (error) {
      toast.error(t("diagnostics.failed"), {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("diagnostics.title")}</CardTitle>
        <CardDescription>{t("diagnostics.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void handleDownload()}
        >
          {busy ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <FileWarning aria-hidden="true" />
          )}
          {busy ? t("diagnostics.preparing") : t("diagnostics.download")}
        </Button>
      </CardContent>
    </Card>
  );
}

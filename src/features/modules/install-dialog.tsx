import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Package, ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { formatBytes } from "./format";
import { ModuleIdentity } from "./manifest-summary";
import { permissionLabel } from "./permission-utils";
import { PermissionChecklist } from "./permission-list";
import type { ModulePreview } from "./types";

interface InstallDialogProps {
  open: boolean;
  preview: ModulePreview | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onClose: () => void;
  onRetry: () => void;
  onConfirm: (permissions: string[], enable: boolean) => void;
}

function initialSelection(preview: ModulePreview): Set<string> {
  const upgrade = preview.alreadyInstalled;
  return new Set(
    preview.permissionDetails
      .filter((item) => item.risk !== "high")
      .filter((item) => !upgrade || !preview.newPermissions.includes(item.scope))
      .map((item) => item.scope),
  );
}

export function InstallDialog({
  open,
  preview,
  loading,
  error,
  busy,
  onClose,
  onRetry,
  onConfirm,
}: InstallDialogProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [enable, setEnable] = useState(true);

  useEffect(() => {
    if (!preview) {
      setSelected(new Set());
      return;
    }
    setSelected(initialSelection(preview));
    setEnable(true);
  }, [preview]);

  const highRisk = preview
    ? preview.permissionDetails.filter((item) => item.risk === "high")
    : [];
  const highRiskSelected = highRisk.some((item) => selected.has(item.scope));
  const sameVersion =
    preview?.alreadyInstalled === true && preview.installedVersion === preview.version;

  function toggle(scope: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent className="sm:max-w-2xl" showCloseButton={!busy}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="size-4" aria-hidden="true" />
            {t("moduleUi.installFlow.title")}
          </DialogTitle>
          <DialogDescription>{t("moduleUi.installFlow.description")}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
          {loading ? (
            <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {t("moduleUi.installFlow.previewing")}
            </div>
          ) : null}

          {!loading && error ? (
            <Alert variant="destructive">
              <ShieldAlert aria-hidden="true" />
              <AlertTitle>{t("moduleUi.installFlow.previewFailed")}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                {t("common.retry")}
              </Button>
            </Alert>
          ) : null}

          {!loading && !error && preview ? (
            <>
              <ModuleIdentity
                name={preview.name}
                id={preview.id}
                version={preview.version}
                type={preview.type}
                description={preview.description}
                author={preview.author}
                license={preview.license}
              />

              <div className="eh-caption flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                <span>
                  {t("moduleUi.installFlow.packageSize", {
                    size: formatBytes(preview.packageBytes),
                  })}
                </span>
                <span>
                  {t("moduleUi.installFlow.compatibility", {
                    range: preview.engines.eclipse,
                  })}
                </span>
              </div>

              {preview.alreadyInstalled ? (
                <Alert variant={sameVersion ? "destructive" : "default"}>
                  <ShieldAlert aria-hidden="true" />
                  <AlertTitle>
                    {sameVersion
                      ? t("moduleUi.installFlow.sameVersion")
                      : t("moduleUi.installFlow.alreadyInstalled", {
                          version: preview.installedVersion ?? "—",
                        })}
                  </AlertTitle>
                </Alert>
              ) : null}

              {preview.warnings.length > 0 ? (
                <Alert>
                  <AlertTitle>{t("moduleUi.installFlow.warnings")}</AlertTitle>
                  <AlertDescription>
                    <ul className="list-inside list-disc">
                      {preview.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}

              <section className="space-y-2">
                <div>
                  <h4 className="eh-caption text-muted-foreground">
                    {t("moduleUi.installFlow.permissions")}
                  </h4>
                  <p className="eh-caption text-muted-foreground">
                    {t("moduleUi.installFlow.permissionsDesc")}
                  </p>
                </div>
                {highRisk.length > 0 ? (
                  <Alert variant="destructive">
                    <ShieldAlert aria-hidden="true" />
                    <AlertTitle>{t("moduleUi.permissions.risk.high")}</AlertTitle>
                    <AlertDescription>
                      {t("moduleUi.installFlow.highRiskHint", {
                        scopes: highRisk
                          .map((item) => permissionLabel(t, item))
                          .join(", "),
                      })}
                    </AlertDescription>
                  </Alert>
                ) : null}
                {preview.alreadyInstalled && preview.newPermissions.length > 0 ? (
                  <p className="eh-caption text-muted-foreground">
                    {t("moduleUi.installFlow.newPermissionHint")}
                  </p>
                ) : null}
                <PermissionChecklist
                  permissions={preview.permissionDetails}
                  selected={selected}
                  newScopes={preview.newPermissions}
                  onToggle={toggle}
                />
              </section>

              <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
                <div className="min-w-0">
                  <Label htmlFor="module-enable-after" className="text-sm font-medium">
                    {t("moduleUi.installFlow.enableAfter")}
                  </Label>
                  <p className="eh-caption text-muted-foreground">
                    {t("moduleUi.installFlow.enableAfterDesc")}
                  </p>
                </div>
                <Switch
                  id="module-enable-after"
                  checked={enable}
                  onCheckedChange={setEnable}
                  disabled={busy}
                />
              </div>
            </>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
            {t("moduleUi.installFlow.cancel")}
          </Button>
          <Button
            type="button"
            disabled={busy || loading || Boolean(error) || !preview || sameVersion}
            onClick={() => onConfirm([...selected], enable)}
          >
            {busy ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Package aria-hidden="true" />
            )}
            {busy
              ? t("moduleUi.installFlow.installing")
              : highRiskSelected
                ? t("moduleUi.installFlow.installWithRisk")
                : t("moduleUi.installFlow.install")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

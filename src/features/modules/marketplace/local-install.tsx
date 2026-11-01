import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { FileArchive, Loader2, Package, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
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
import { installModulePackage, previewModulePackage } from "../api";
import { moduleErrorMessage } from "../errors";
import { formatBytes } from "../format";
import { ModuleIdentity } from "../manifest-summary";
import { permissionLabel } from "../permission-utils";
import { PermissionChecklist } from "../permission-list";
import type { ModulePreview } from "../types";

interface LocalInstallProps {
  onInstalled: () => void;
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

/**
 * 本地 .ehmod 安装：保留原有的“选择文件 → 预览 → 确认权限 → 安装”流程，
 * 只是从页头按钮移进安装对话框的第三个 tab。
 */
export function LocalInstall({ onInstalled }: LocalInstallProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ModulePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
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

  async function loadPreview(file: File) {
    setPreviewLoading(true);
    setPreviewError(null);
    setPreview(null);
    try {
      setPreview(await previewModulePackage(file));
    } catch (error) {
      setPreviewError(moduleErrorMessage(error, t));
    } finally {
      setPreviewLoading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".ehmod")) {
      toast.error(t("moduleUi.errors.invalidPackage"));
      return;
    }
    setPendingFile(file);
    void loadPreview(file);
  }

  function closePreview() {
    if (installBusy) return;
    setPendingFile(null);
    setPreview(null);
    setPreviewError(null);
  }

  async function handleInstall() {
    if (!pendingFile) return;
    setInstallBusy(true);
    try {
      const installed = await installModulePackage(pendingFile, {
        permissions: [...selected],
        enable,
      });
      toast.success(
        preview?.alreadyInstalled === true
          ? t("moduleUi.installFlow.successUpgrade", {
              name: installed.name,
              version: installed.version,
            })
          : t("moduleUi.installFlow.success", { name: installed.name }),
      );
      setPendingFile(null);
      setPreview(null);
      onInstalled();
    } catch (error) {
      toast.error(t("moduleUi.toast.actionFailed"), {
        description: moduleErrorMessage(error, t),
      });
    } finally {
      setInstallBusy(false);
    }
  }

  function toggle(scope: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  const highRisk = preview
    ? preview.permissionDetails.filter((item) => item.risk === "high")
    : [];
  const highRiskSelected = highRisk.some((item) => selected.has(item.scope));
  const sameVersion =
    preview?.alreadyInstalled === true && preview.installedVersion === preview.version;

  return (
    <>
      <div className="rounded-xl border border-dashed border-border bg-surface/60 px-6 py-10 text-center">
        <div
          className="mx-auto mb-3 flex size-11 items-center justify-center rounded-full bg-subtle text-muted-foreground"
          aria-hidden="true"
        >
          <FileArchive className="size-5" />
        </div>
        <h3 className="eh-h3">{t("moduleUi.marketplace.local.title")}</h3>
        <p className="eh-small mx-auto mt-2 max-w-[52ch] text-muted-foreground">
          {t("moduleUi.marketplace.local.description")}
        </p>
        <Button
          type="button"
          variant="outline"
          className="mt-4"
          disabled={installBusy}
          onClick={() => fileInputRef.current?.click()}
        >
          <FileArchive aria-hidden="true" />
          {t("moduleUi.marketplace.local.choose")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".ehmod,application/zip"
          className="sr-only"
          onChange={handleFileChange}
        />
      </div>

      <Dialog
        open={pendingFile !== null}
        onOpenChange={(next) => {
          if (!next && !installBusy) closePreview();
        }}
      >
        <DialogContent className="sm:max-w-2xl" showCloseButton={!installBusy}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Package className="size-4" aria-hidden="true" />
              {t("moduleUi.installFlow.title")}
            </DialogTitle>
            <DialogDescription>
              {t("moduleUi.installFlow.description")}
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
            {previewLoading ? (
              <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                {t("moduleUi.installFlow.previewing")}
              </div>
            ) : null}

            {!previewLoading && previewError ? (
              <Alert variant="destructive">
                <ShieldAlert aria-hidden="true" />
                <AlertTitle>{t("moduleUi.installFlow.previewFailed")}</AlertTitle>
                <AlertDescription>{previewError}</AlertDescription>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (pendingFile) void loadPreview(pendingFile);
                  }}
                >
                  {t("common.retry")}
                </Button>
              </Alert>
            ) : null}

            {!previewLoading && !previewError && preview ? (
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
                    <Label htmlFor="module-local-enable-after" className="text-sm font-medium">
                      {t("moduleUi.installFlow.enableAfter")}
                    </Label>
                    <p className="eh-caption text-muted-foreground">
                      {t("moduleUi.installFlow.enableAfterDesc")}
                    </p>
                  </div>
                  <Switch
                    id="module-local-enable-after"
                    checked={enable}
                    onCheckedChange={setEnable}
                    disabled={installBusy}
                  />
                </div>
              </>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={installBusy}
              onClick={closePreview}
            >
              {t("moduleUi.installFlow.cancel")}
            </Button>
            <Button
              type="button"
              disabled={
                installBusy ||
                previewLoading ||
                Boolean(previewError) ||
                !preview ||
                sameVersion
              }
              onClick={() => void handleInstall()}
            >
              {installBusy ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Package aria-hidden="true" />
              )}
              {installBusy
                ? t("moduleUi.installFlow.installing")
                : highRiskSelected
                  ? t("moduleUi.installFlow.installWithRisk")
                  : t("moduleUi.installFlow.install")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

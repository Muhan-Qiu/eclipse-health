import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import {
  Download,
  ExternalLink,
  GitBranch,
  Loader2,
  Package,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatBytes, moduleTypeLabel } from "../format";
import {
  permissionDescription,
  permissionLabel,
  riskLabel,
  riskVariant,
} from "../permission-utils";
import type { PermissionDetail, PermissionRisk } from "../types";
import {
  installMarketplaceModule,
  marketplaceErrorMessage,
} from "./api";
import type { MarketplaceModule, MarketplaceSource } from "./types";

interface ModuleDetailDialogProps {
  source: MarketplaceSource;
  module: MarketplaceModule | null;
  installedVersion: string | null;
  open: boolean;
  onClose: () => void;
  onInstalled: (module: MarketplaceModule) => void;
}

const MEDIUM_RISK = new Set([
  "records_write",
  "network",
  "llm",
  "models_download",
  "ui_custom",
  "system_background",
]);

/** 索引只给权限 scope，没有风险分级；这里用保守的本地映射补齐展示。 */
function permissionDetails(scopes: string[]): PermissionDetail[] {
  return scopes.map((scope) => {
    const risk: PermissionRisk =
      scope === "records_delete"
        ? "high"
        : MEDIUM_RISK.has(scope)
          ? "medium"
          : "low";
    return { scope, risk, label: scope, description: "" };
  });
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="eh-caption shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right text-sm">{children}</dd>
    </div>
  );
}

function permissionItems(module: MarketplaceModule): PermissionDetail[] {
  return permissionDetails(module.permissions ?? []);
}

export function ModuleDetailDialog({
  source,
  module,
  installedVersion,
  open,
  onClose,
  onInstalled,
}: ModuleDetailDialogProps) {
  const { t } = useTranslation();

  const install = useMutation({
    mutationFn: () => {
      if (!module) throw new Error("missing module");
      return installMarketplaceModule({
        source,
        moduleId: module.id,
        version: module.version,
      });
    },
    onSuccess: (installed) => {
      if (module) {
        const isUpdate = installedVersion !== null && installedVersion !== module.version;
        toast.success(
          isUpdate
            ? t("moduleUi.marketplace.toast.updated", {
                name: installed.name || module.name,
                version: module.version,
              })
            : t("moduleUi.marketplace.toast.installed", {
                name: installed.name || module.name,
              }),
        );
        onInstalled(module);
      }
      onClose();
    },
  });

  if (!module) return null;

  const sameVersion = installedVersion === module.version;
  const isUpdate = installedVersion !== null && !sameVersion;
  const community = source === "community";
  const permissions = permissionItems(module);
  const dependencies = module.dependencies ?? [];

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !install.isPending) onClose();
      }}
    >
      <DialogContent className="sm:max-w-2xl" showCloseButton={!install.isPending}>
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2 pr-8">
            <Package className="size-4" aria-hidden="true" />
            {module.name}
            {module.verified ? (
              <Badge variant="secondary" className="gap-1 font-normal">
                <ShieldCheck className="size-3" aria-hidden="true" />
                {t("moduleUi.marketplace.verified")}
              </Badge>
            ) : null}
            {community ? (
              <Badge variant="outline" className="gap-1 font-normal">
                <ShieldAlert className="size-3" aria-hidden="true" />
                {t("moduleUi.marketplace.unreviewed")}
              </Badge>
            ) : null}
          </DialogTitle>
          <DialogDescription className="space-y-1">
            <code className="eh-caption block">{module.id}</code>
            {module.description ? <span>{module.description}</span> : null}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
          {community ? (
            <Alert variant="destructive">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>{t("moduleUi.marketplace.unreviewed")}</AlertTitle>
              <AlertDescription>
                {t("moduleUi.marketplace.details.communityWarning")}
              </AlertDescription>
            </Alert>
          ) : null}

          <dl className="divide-y divide-border overflow-hidden rounded-lg border border-border px-3">
            <Fact label={t("moduleUi.manifest.version")}>v{module.version}</Fact>
            {module.type ? (
              <Fact label={t("moduleUi.manifest.type")}>
                {moduleTypeLabel(t, module.type)}
              </Fact>
            ) : null}
            {module.author ? (
              <Fact label={t("moduleUi.manifest.author")}>{module.author}</Fact>
            ) : null}
            <Fact label={t("moduleUi.manifest.license")}>
              {module.license ?? "—"}
            </Fact>
            {typeof module.size === "number" && module.size > 0 ? (
              <Fact label={t("moduleUi.marketplace.details.size")}>
                {formatBytes(module.size)}
              </Fact>
            ) : null}
            {module.minCoreVersion ? (
              <Fact label={t("moduleUi.marketplace.details.minCore")}>
                {module.minCoreVersion}
              </Fact>
            ) : null}
            {module.categories && module.categories.length > 0 ? (
              <Fact label={t("moduleUi.marketplace.details.categories")}>
                <span className="flex flex-wrap justify-end gap-1">
                  {module.categories.map((category) => (
                    <Badge
                      key={category}
                      variant="outline"
                      className="font-normal text-muted-foreground"
                    >
                      {category}
                    </Badge>
                  ))}
                </span>
              </Fact>
            ) : null}
          </dl>

          {module.repository ? (
            <a
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              href={module.repository}
              target="_blank"
              rel="noreferrer"
            >
              <GitBranch className="size-3.5" aria-hidden="true" />
              {t("moduleUi.manifest.repository")}
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>
          ) : null}

          <section className="space-y-2">
            <h4 className="eh-caption text-muted-foreground">
              {t("moduleUi.marketplace.details.permissions", {
                count: permissions.length,
              })}
            </h4>
            {permissions.length === 0 ? (
              <p className="eh-small rounded-lg border border-dashed border-border p-3 text-muted-foreground">
                {t("moduleUi.marketplace.details.noPermissions")}
              </p>
            ) : (
              <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                {permissions.map((item) => (
                  <li key={item.scope} className="flex gap-3 p-3">
                    <ShieldCheck
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          {permissionLabel(t, item)}
                        </span>
                        <Badge
                          variant={riskVariant(item.risk)}
                          className="font-normal"
                        >
                          {riskLabel(t, item.risk)}
                        </Badge>
                        <code className="eh-caption text-muted-foreground">
                          {item.scope}
                        </code>
                      </div>
                      <p className="eh-caption mt-1 text-muted-foreground">
                        {permissionDescription(t, item)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="eh-caption text-muted-foreground">
              {t("moduleUi.marketplace.details.dependencies", {
                count: dependencies.length,
              })}
            </h4>
            {dependencies.length === 0 ? (
              <p className="eh-small text-muted-foreground">
                {t("moduleUi.marketplace.details.noDependencies")}
              </p>
            ) : (
              <>
                <ul className="flex flex-wrap gap-1.5">
                  {dependencies.map((dependency) => (
                    <li key={dependency}>
                      <Badge variant="outline" className="font-normal">
                        {dependency}
                      </Badge>
                    </li>
                  ))}
                </ul>
                <p className="eh-caption text-muted-foreground">
                  {t("moduleUi.marketplace.details.dependencyHint")}
                </p>
              </>
            )}
          </section>

          {install.isPending ? (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <p className="eh-small flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                {t("moduleUi.marketplace.details.installing")}
              </p>
              <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-primary" />
              </div>
            </div>
          ) : null}

          {install.isError ? (
            <Alert variant="destructive">
              <ShieldAlert aria-hidden="true" />
              <AlertTitle>{t("moduleUi.marketplace.details.installFailed")}</AlertTitle>
              <AlertDescription>
                {marketplaceErrorMessage(install.error, t)}
              </AlertDescription>
            </Alert>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={install.isPending}
            onClick={onClose}
          >
            {t("moduleUi.installFlow.cancel")}
          </Button>
          <Button
            type="button"
            disabled={install.isPending || sameVersion}
            onClick={() => install.mutate()}
          >
            {install.isPending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Download aria-hidden="true" />
            )}
            {sameVersion
              ? t("moduleUi.marketplace.installedBadge")
              : isUpdate
                ? t("moduleUi.marketplace.update")
                : t("moduleUi.marketplace.install")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ExternalLink, Layers } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { moduleTypeLabel } from "./format";
import type {
  ModuleAuthor,
  ModuleManifest,
  ModuleResources,
} from "./types";

interface ModuleIdentityProps {
  name: string;
  id: string;
  version: string;
  type: string;
  description: string;
  author?: ModuleAuthor;
  license?: string;
  showCredits?: boolean;
}

export function ModuleIdentity({
  name,
  id,
  version,
  type,
  description,
  author,
  license,
  showCredits = true,
}: ModuleIdentityProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="eh-h3">{name}</h3>
        <Badge variant="secondary" className="font-normal">
          v{version}
        </Badge>
        <Badge variant="outline" className="font-normal text-muted-foreground">
          {moduleTypeLabel(t, type)}
        </Badge>
      </div>
      <code className="eh-caption block text-muted-foreground">{id}</code>
      <p className="eh-small text-muted-foreground">{description}</p>
      {showCredits && (author || license) ? (
        <p className="eh-caption text-muted-foreground">
          {author ? t("moduleUi.manifest.author") + " " + author.name : null}
          {author && license ? " · " : null}
          {license ? t("moduleUi.manifest.license") + " " + license : null}
        </p>
      ) : null}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="eh-caption text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words text-sm">{children}</dd>
    </div>
  );
}

function resourceLabels(t: TFunction, resources: ModuleResources) {
  const labels: string[] = [];
  if (typeof resources.memoryMb === "number") {
    labels.push(t("moduleUi.manifest.memory", { value: resources.memoryMb }));
  }
  if (typeof resources.cpu === "number") {
    labels.push(t("moduleUi.manifest.cpu", { value: resources.cpu }));
  }
  if (typeof resources.startupTimeoutMs === "number") {
    labels.push(
      t("moduleUi.manifest.startupTimeout", { value: resources.startupTimeoutMs }),
    );
  }
  return labels;
}

interface ContributionItem {
  id?: string;
  name?: string;
  description?: string;
  extras: [string, string][];
}

function contributionItems(value: unknown): ContributionItem[] {
  if (!Array.isArray(value)) return [];
  const items: ContributionItem[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const extras: [string, string][] = [];
    for (const [key, raw] of Object.entries(record)) {
      if (key === "id" || key === "name" || key === "description") continue;
      if (typeof raw === "string" || typeof raw === "number") {
        extras.push([key, String(raw)]);
      }
    }
    items.push({
      id: typeof record.id === "string" ? record.id : undefined,
      name: typeof record.name === "string" ? record.name : undefined,
      description:
        typeof record.description === "string" ? record.description : undefined,
      extras,
    });
  }
  return items;
}

interface ManifestFactsProps {
  manifest: ModuleManifest;
}

export function ManifestFacts({ manifest }: ManifestFactsProps) {
  const { t } = useTranslation();
  const resources = resourceLabels(t, manifest.resources);
  const contributions = Object.entries(manifest.contributes)
    .map(([key, value]) => ({ key, items: contributionItems(value) }))
    .filter((group) => group.items.length > 0);

  return (
    <div className="space-y-5">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <Fact label={t("moduleUi.manifest.author")}>
          {manifest.author.name || "—"}
        </Fact>
        <Fact label={t("moduleUi.manifest.license")}>{manifest.license || "—"}</Fact>
        <Fact label={t("moduleUi.manifest.apiVersion")}>{manifest.apiVersion}</Fact>
        <Fact label={t("moduleUi.manifest.engines")}>{manifest.engines.eclipse}</Fact>
        <Fact label={t("moduleUi.manifest.updateChannel")}>
          {manifest.updateChannel || "—"}
        </Fact>
        <Fact label={t("moduleUi.manifest.resources")}>
          {resources.length > 0 ? (
            <span className="flex flex-wrap gap-1">
              {resources.map((label) => (
                <Badge key={label} variant="outline" className="font-normal">
                  {label}
                </Badge>
              ))}
            </span>
          ) : (
            <span className="text-muted-foreground">
              {t("moduleUi.manifest.noResources")}
            </span>
          )}
        </Fact>
      </dl>

      {manifest.homepage || manifest.repository ? (
        <div className="flex flex-wrap gap-4 text-sm">
          {manifest.homepage ? (
            <a
              className="inline-flex items-center gap-1 text-primary hover:underline"
              href={manifest.homepage}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink className="size-3.5" aria-hidden="true" />
              {t("moduleUi.manifest.homepage")}
            </a>
          ) : null}
          {manifest.repository ? (
            <a
              className="inline-flex items-center gap-1 text-primary hover:underline"
              href={manifest.repository}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink className="size-3.5" aria-hidden="true" />
              {t("moduleUi.manifest.repository")}
            </a>
          ) : null}
        </div>
      ) : null}

      <section>
        <h4 className="eh-caption mb-2 flex items-center gap-1.5 text-muted-foreground">
          <Layers className="size-3.5" aria-hidden="true" />
          {t("moduleUi.manifest.contributions")}
        </h4>
        {contributions.length === 0 ? (
          <p className="eh-small text-muted-foreground">
            {t("moduleUi.manifest.noContributions")}
          </p>
        ) : (
          <div className="space-y-2">
            {contributions.map((group) => (
              <div
                key={group.key}
                className="rounded-lg border border-border bg-muted/20 p-3"
              >
                <code className="eh-caption text-muted-foreground">{group.key}</code>
                <ul className="mt-1.5 space-y-1.5">
                  {group.items.map((item, index) => (
                    <li key={`${group.key}-${item.id ?? index}`} className="text-sm">
                      <span className="font-medium">
                        {item.name ?? item.id ?? "—"}
                      </span>
                      {item.id && item.name ? (
                        <code className="eh-caption ml-2 text-muted-foreground">
                          {item.id}
                        </code>
                      ) : null}
                      {item.description ? (
                        <p className="eh-caption text-muted-foreground">
                          {item.description}
                        </p>
                      ) : null}
                      {item.extras.length > 0 ? (
                        <p className="eh-caption mt-0.5 flex flex-wrap gap-x-3 text-muted-foreground">
                          {item.extras.map(([key, value]) => (
                            <span key={key}>
                              {key}: {value}
                            </span>
                          ))}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

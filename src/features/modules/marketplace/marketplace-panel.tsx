import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Store,
  Users,
  FileArchive,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { moduleTypeLabel } from "../format";
import type { ModuleSummary } from "../types";
import {
  MARKETPLACE_SOURCES_KEY,
  getMarketplaceIndex,
  getMarketplaceSources,
  isMarketplaceNotConfigured,
  marketplaceErrorMessage,
  marketplaceIndexKey,
} from "./api";
import { LocalInstall } from "./local-install";
import { ModuleDetailDialog } from "./module-detail-dialog";
import type {
  MarketplaceModule,
  MarketplaceSource,
  MarketplaceSourceInfo,
  MarketplaceTab,
} from "./types";

interface MarketplacePanelProps {
  open: boolean;
  initialTab?: MarketplaceTab;
  installed: ModuleSummary[];
  onInstalled: () => void;
}

function isNewerVersion(available: string, installed: string): boolean {
  const left = available.split(/[.+-]/).map((part) => Number.parseInt(part, 10));
  const right = installed.split(/[.+-]/).map((part) => Number.parseInt(part, 10));
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const a = Number.isFinite(left[index]) ? left[index] : 0;
    const b = Number.isFinite(right[index]) ? right[index] : 0;
    if (a !== b) return a > b;
  }
  return false;
}

interface MarketplaceBrowserProps {
  source: MarketplaceSource;
  open: boolean;
  info: MarketplaceSourceInfo | undefined;
  installed: Map<string, string>;
  onSelect: (module: MarketplaceModule) => void;
}

function MarketplaceBrowser({
  source,
  open,
  info,
  installed,
  onSelect,
}: MarketplaceBrowserProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const activeCategory = category === "all" ? "" : category;
  const indexQuery = useQuery({
    queryKey: marketplaceIndexKey(source, query, activeCategory),
    queryFn: () => getMarketplaceIndex(source, query, activeCategory),
    enabled: open && info?.configured !== false,
    retry: false,
  });

  const modules = indexQuery.data?.modules ?? [];
  // 分类选项累积自所有已加载响应：分类筛选后响应只剩当前分类，
  // 若直接从当前列表派生，选项会塌缩并导致选中值被重置。
  const [knownCategories, setKnownCategories] = useState<string[]>([]);
  useEffect(() => {
    if (!indexQuery.data) return;
    setKnownCategories((current) => {
      const next = new Set(current);
      for (const module of indexQuery.data.modules) {
        for (const value of module.categories ?? []) next.add(value);
      }
      return next.size === current.length ? current : [...next].sort();
    });
  }, [indexQuery.data]);

  useEffect(() => {
    if (
      activeCategory &&
      knownCategories.length > 0 &&
      !knownCategories.includes(activeCategory)
    ) {
      setCategory("all");
    }
  }, [activeCategory, knownCategories]);

  if (info?.configured === false) {
    return (
      <EmptyState
        icon={Store}
        title={t("moduleUi.marketplace.notConfiguredTitle")}
        description={t("moduleUi.marketplace.notConfiguredDesc", {
          source: t(`moduleUi.marketplace.tabs.${source}`),
        })}
      />
    );
  }

  const notConfiguredError =
    indexQuery.isError && isMarketplaceNotConfigured(indexQuery.error);

  return (
    <div className="space-y-3">
      {source === "community" ? (
        <Alert variant="destructive">
          <ShieldAlert aria-hidden="true" />
          <AlertTitle>{t("moduleUi.marketplace.unreviewed")}</AlertTitle>
          <AlertDescription>
            {t("moduleUi.marketplace.unreviewedHint")}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("moduleUi.marketplace.searchPlaceholder")}
            aria-label={t("moduleUi.marketplace.searchPlaceholder")}
            className="pl-8"
          />
        </div>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger
            size="sm"
            className="w-[10rem]"
            aria-label={t("moduleUi.marketplace.category")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">
              {t("moduleUi.marketplace.allCategories")}
            </SelectItem>
            {knownCategories.map((value) => (
              <SelectItem key={value} value={value}>
                {value}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("moduleUi.marketplace.refresh")}
          disabled={indexQuery.isFetching}
          onClick={() => void indexQuery.refetch()}
        >
          {indexQuery.isFetching ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw aria-hidden="true" />
          )}
        </Button>
      </div>

      {notConfiguredError ? (
        <EmptyState
          icon={Store}
          title={t("moduleUi.marketplace.notConfiguredTitle")}
          description={t("moduleUi.marketplace.notConfiguredDesc", {
            source: t(`moduleUi.marketplace.tabs.${source}`),
          })}
        />
      ) : null}

      {indexQuery.isError && !notConfiguredError ? (
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("moduleUi.marketplace.loadError")}</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{marketplaceErrorMessage(indexQuery.error, t)}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void indexQuery.refetch()}
            >
              {t("common.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {!notConfiguredError && indexQuery.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-32 w-full" />
          ))}
        </div>
      ) : null}

      {!notConfiguredError &&
      !indexQuery.isLoading &&
      !indexQuery.isError &&
      modules.length === 0 ? (
        <EmptyState
          icon={Store}
          title={t("moduleUi.marketplace.empty")}
          description={t("moduleUi.marketplace.emptyDesc")}
        />
      ) : null}

      {modules.length > 0 ? (
        <ul className="grid gap-3 sm:grid-cols-2">
          {modules.map((module) => {
            const installedVersion = installed.get(module.id);
            const sameVersion = installedVersion === module.version;
            const update =
              installedVersion !== undefined &&
              !sameVersion &&
              isNewerVersion(module.version, installedVersion);
            return (
              <li key={module.id}>
                <button
                  type="button"
                  onClick={() => onSelect(module)}
                  className="group flex h-full w-full flex-col gap-2 rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent-soft/40 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <span className="flex w-full items-start justify-between gap-2">
                    <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                      <span className="truncate text-sm font-medium">{module.name}</span>
                      {module.verified ? (
                        <Badge variant="secondary" className="gap-1 font-normal">
                          <ShieldCheck className="size-3" aria-hidden="true" />
                          {t("moduleUi.marketplace.verified")}
                        </Badge>
                      ) : null}
                      {source === "community" ? (
                        <Badge variant="outline" className="gap-1 font-normal">
                          <ShieldAlert className="size-3" aria-hidden="true" />
                          {t("moduleUi.marketplace.unreviewed")}
                        </Badge>
                      ) : null}
                    </span>
                    <Badge variant="secondary" className="shrink-0 font-normal">
                      v{module.version}
                    </Badge>
                  </span>

                  <code className="eh-caption block truncate text-muted-foreground">
                    {module.id}
                  </code>

                  {module.description ? (
                    <span className="eh-small line-clamp-2 text-muted-foreground">
                      {module.description}
                    </span>
                  ) : null}

                  <span className="eh-caption mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                    {module.type ? (
                      <span>{moduleTypeLabel(t, module.type)}</span>
                    ) : null}
                    {module.author ? <span>{module.author}</span> : null}
                    {module.license ? <span>{module.license}</span> : null}
                    <span>
                      {t("moduleUi.marketplace.permissionCount", {
                        count: module.permissions?.length ?? 0,
                      })}
                    </span>
                  </span>

                  <span className="mt-1 flex items-center justify-between gap-2">
                    <span className="flex flex-wrap gap-1">
                      {sameVersion ? (
                        <Badge variant="outline" className="font-normal">
                          {t("moduleUi.marketplace.installedBadge")}
                        </Badge>
                      ) : update ? (
                        <Badge variant="default" className="font-normal">
                          {t("moduleUi.marketplace.updateBadge")}
                        </Badge>
                      ) : installedVersion ? (
                        <Badge
                          variant="outline"
                          className="font-normal text-muted-foreground"
                        >
                          v{installedVersion}
                        </Badge>
                      ) : null}
                    </span>
                    <span className="eh-caption text-primary group-hover:underline">
                      {t("moduleUi.marketplace.viewDetails")}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export function MarketplacePanel({
  open,
  initialTab,
  installed,
  onInstalled,
}: MarketplacePanelProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<MarketplaceTab>(initialTab ?? "official");
  const [selected, setSelected] = useState<{
    source: MarketplaceSource;
    module: MarketplaceModule;
  } | null>(null);

  useEffect(() => {
    if (open && initialTab) setTab(initialTab);
  }, [open, initialTab]);

  const sourcesQuery = useQuery({
    queryKey: MARKETPLACE_SOURCES_KEY,
    queryFn: getMarketplaceSources,
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  const installedMap = useMemo(
    () => new Map(installed.map((module) => [module.id, module.version])),
    [installed],
  );

  const sourceInfo = (source: MarketplaceSource) => sourcesQuery.data?.[source];

  return (
    <>
      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as MarketplaceTab)}
        className="min-h-0"
      >
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="official">
            <Store aria-hidden="true" />
            {t("moduleUi.marketplace.tabs.official")}
          </TabsTrigger>
          <TabsTrigger value="community">
            <Users aria-hidden="true" />
            {t("moduleUi.marketplace.tabs.community")}
          </TabsTrigger>
          <TabsTrigger value="local">
            <FileArchive aria-hidden="true" />
            {t("moduleUi.marketplace.tabs.local")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="official" className="mt-3 max-h-[58vh] overflow-y-auto pr-1">
          {sourcesQuery.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-32 w-full" />
              ))}
            </div>
          ) : (
            <MarketplaceBrowser
              source="official"
              open={open}
              info={sourceInfo("official")}
              installed={installedMap}
              onSelect={(module) => setSelected({ source: "official", module })}
            />
          )}
        </TabsContent>

        <TabsContent value="community" className="mt-3 max-h-[58vh] overflow-y-auto pr-1">
          {sourcesQuery.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-32 w-full" />
              ))}
            </div>
          ) : (
            <MarketplaceBrowser
              source="community"
              open={open}
              info={sourceInfo("community")}
              installed={installedMap}
              onSelect={(module) => setSelected({ source: "community", module })}
            />
          )}
        </TabsContent>

        <TabsContent value="local" className="mt-3 max-h-[58vh] overflow-y-auto pr-1">
          <LocalInstall onInstalled={onInstalled} />
        </TabsContent>
      </Tabs>

      <ModuleDetailDialog
        source={selected?.source ?? "official"}
        module={selected?.module ?? null}
        open={selected !== null}
        installedVersion={
          selected ? installedMap.get(selected.module.id) ?? null : null
        }
        onClose={() => setSelected(null)}
        onInstalled={onInstalled}
      />
    </>
  );
}

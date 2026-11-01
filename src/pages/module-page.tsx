import "@/features/modules/pages/i18n";

import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  FileQuestion,
  PowerOff,
  RefreshCw,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import {
  MODULE_QUERY_KEY,
  listModules,
} from "@/features/modules/api";
import type { ModuleSummary } from "@/features/modules/types";
import {
  PAGE_CONTRIBUTIONS_KEY,
  listPageContributions,
} from "@/features/modules/pages/page-api";
import { PageLayout } from "@/features/modules/pages/page-layout";

function ModulePageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-7 w-56" />
      </div>
      <Skeleton className="h-24 w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    </div>
  );
}

function BackToModules() {
  const { t } = useTranslation();
  return (
    <Button variant="outline" size="sm" asChild>
      <Link to="/modules">
        <ArrowLeft aria-hidden="true" />
        {t("modulePage.backToModules")}
      </Link>
    </Button>
  );
}

function UnavailablePage({
  icon,
  title,
  description,
}: {
  icon: typeof FileQuestion;
  title: string;
  description: string;
}) {
  return (
    <EmptyState icon={icon} title={title} description={description}>
      <BackToModules />
    </EmptyState>
  );
}

export function ModulePage() {
  const { moduleId = "", pageId = "" } = useParams<{
    moduleId: string;
    pageId: string;
  }>();
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const pagesQuery = useQuery({
    queryKey: PAGE_CONTRIBUTIONS_KEY,
    queryFn: listPageContributions,
    // 页面是否可见取决于模块的 enabled 状态，避免沿用旧的空列表。
    staleTime: 0,
  });
  const modulesQuery = useQuery<ModuleSummary[]>({
    queryKey: MODULE_QUERY_KEY,
    queryFn: listModules,
  });

  const page = pagesQuery.data?.find(
    (item) => item.moduleId === moduleId && item.id === pageId,
  );
  const moduleInfo = modulesQuery.data?.find((item) => item.id === moduleId);

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: ["modules", "page-rpc", moduleId],
    });
    void pagesQuery.refetch();
  }

  if (pagesQuery.isPending) return <ModulePageSkeleton />;

  if (pagesQuery.isError) {
    return (
      <>
        <PageHeader
          eyebrow={t("modulePage.eyebrow")}
          title={t("modulePage.loadError")}
          description={t("modulePage.loadErrorDesc")}
          actions={<BackToModules />}
        />
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("modulePage.loadError")}</AlertTitle>
          <AlertDescription>{t("modulePage.loadErrorDesc")}</AlertDescription>
        </Alert>
        <div className="mt-4">
          <Button variant="outline" onClick={() => void pagesQuery.refetch()}>
            <RefreshCw aria-hidden="true" />
            {t("common.retry")}
          </Button>
        </div>
      </>
    );
  }

  if (!page) {
    if (modulesQuery.isPending) return <ModulePageSkeleton />;
    if (!moduleInfo && !modulesQuery.isError) {
      return (
        <UnavailablePage
          icon={FileQuestion}
          title={t("modulePage.missingModuleTitle")}
          description={t("modulePage.missingModuleDesc")}
        />
      );
    }
    if (moduleInfo && !moduleInfo.enabled) {
      return (
        <UnavailablePage
          icon={PowerOff}
          title={t("modulePage.disabledTitle")}
          description={t("modulePage.disabledDesc")}
        />
      );
    }
    return (
      <UnavailablePage
        icon={FileQuestion}
        title={t("modulePage.notFoundTitle")}
        description={t("modulePage.notFoundDesc")}
      />
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={page.moduleName}
        title={page.title}
        actions={
          <>
            <BackToModules />
            <Button
              variant="outline"
              size="sm"
              onClick={refresh}
              disabled={pagesQuery.isFetching}
            >
              <RefreshCw
                className={pagesQuery.isFetching ? "animate-spin" : undefined}
                aria-hidden="true"
              />
              {t("modulePage.refresh")}
            </Button>
          </>
        }
      />
      <PageLayout moduleId={page.moduleId} blocks={page.layout} />
    </>
  );
}

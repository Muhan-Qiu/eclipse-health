import type { LucideIcon } from "lucide-react";
import {
  FileChartColumn,
  TrendingUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

interface ComingSoonPageProps {
  pageKey: "trends" | "reports";
  icon: LucideIcon;
  note?: string;
}

function ComingSoonPage({ pageKey, icon, note }: ComingSoonPageProps) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader
        eyebrow={t(`${pageKey}.eyebrow`)}
        title={t(`${pageKey}.title`)}
        description={t(`${pageKey}.description`)}
        actions={
          <Badge variant="outline" className="font-normal text-muted-foreground">
            {t("common.comingSoon")}
          </Badge>
        }
      />
      <EmptyState
        icon={icon}
        title={t(`${pageKey}.emptyTitle`)}
        description={t(`${pageKey}.emptyDesc`)}
      />
      {note ? (
        <p className="eh-caption mt-4 text-center text-muted-foreground">
          {note}
        </p>
      ) : null}
    </>
  );
}

export function TrendsPage() {
  return <ComingSoonPage pageKey="trends" icon={TrendingUp} />;
}

export function ReportsPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      pageKey="reports"
      icon={FileChartColumn}
      note={t("common.localOnly")}
    />
  );
}

/**
 * B3-04 把助手页替换为真实实现；保留这个导出是为了让 `App.tsx`
 * （由 B3-02 拥有）不需要改动。
 */
export { AssistantPage } from "@/pages/assistant";

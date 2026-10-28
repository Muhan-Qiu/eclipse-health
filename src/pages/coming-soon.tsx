import type { LucideIcon } from "lucide-react";
import {
  FileChartColumn,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

interface ComingSoonPageProps {
  pageKey: "trends" | "reports" | "assistant";
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

export function AssistantPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      pageKey="assistant"
      icon={Sparkles}
      note={t("assistant.note")}
    />
  );
}

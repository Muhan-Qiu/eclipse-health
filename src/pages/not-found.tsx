import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader eyebrow="404" title={t("notFound.title")} />
      <EmptyState
        icon={Compass}
        title={t("notFound.title")}
        description={t("notFound.description")}
      >
        <Button asChild size="sm">
          <Link to="/">{t("notFound.action")}</Link>
        </Button>
      </EmptyState>
    </>
  );
}

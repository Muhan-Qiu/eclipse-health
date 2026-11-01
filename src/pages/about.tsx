import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { EclipseMark } from "@/components/common/eclipse-mark";
import { PageHeader } from "@/components/common/page-header";
import { APP_LICENSE, APP_VERSION } from "@/lib/app-info";

const SECTIONS = ["what", "privacy", "stack", "license"] as const;

export function AboutPage() {
  const { t } = useTranslation();

  return (
    <>
      <PageHeader
        eyebrow={t("about.eyebrow")}
        title={t("about.title")}
        description={t("about.description")}
        actions={<EclipseMark className="size-12" />}
      />

      <div className="eh-grid">
        {SECTIONS.map((section) => (
          <Card key={section} className="desk:col-span-4 xl:col-span-6">
            <CardContent className="space-y-2">
              <h2 className="eh-h3">{t(`about.sections.${section}.title`)}</h2>
              <p className="eh-small max-w-[72ch] text-muted-foreground">
                {t(`about.sections.${section}.body`)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="eh-caption mt-6 text-muted-foreground">
        {t("common.version", { version: APP_VERSION })} · {APP_LICENSE} ·{" "}
        {t("common.localOnly")}
      </p>
    </>
  );
}

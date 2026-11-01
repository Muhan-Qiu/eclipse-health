import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import { MetricsPanel } from "@/features/profile/metrics-panel";
import { ProfileForm } from "@/features/profile/profile-form";
import "@/features/profile/i18n";

export function ProfilePage() {
  const { t } = useTranslation();

  return (
    <>
      <PageHeader
        eyebrow={t("profile.eyebrow")}
        title={t("profile.title")}
        description={t("profile.description")}
      />

      <div className="eh-grid">
        <ProfileForm className="desk:col-span-8 xl:col-span-7" />

        <Card className="desk:col-span-4 xl:col-span-5">
          <CardHeader>
            <CardTitle className="eh-h3 flex items-center gap-2">
              <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
              {t("profile.privacy.title")}
            </CardTitle>
            <CardDescription>{t("profile.privacy.description")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="eh-small text-muted-foreground">
              {t("profile.privacy.localOnly")}
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/settings">{t("profile.privacy.openSettings")}</Link>
            </Button>
          </CardContent>
        </Card>

        <MetricsPanel className="desk:col-span-8 xl:col-span-12" />
      </div>
    </>
  );
}

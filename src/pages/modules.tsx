import { useTranslation } from "react-i18next";
import { Blocks, Cpu, Download, Palette } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";

const MODULE_CARDS = [
  { key: "importer", icon: Download, status: "comingSoon" },
  { key: "model", icon: Cpu, status: "preset" },
  { key: "theme", icon: Palette, status: "preset" },
] as const;

export function ModulesPage() {
  const { t } = useTranslation();

  return (
    <>
      <PageHeader
        eyebrow={t("modules.eyebrow")}
        title={t("modules.title")}
        description={t("modules.description")}
        actions={
          <Badge variant="outline" className="font-normal text-muted-foreground">
            {t("common.comingSoon")}
          </Badge>
        }
      />

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div
            className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-primary"
            aria-hidden="true"
          >
            <Blocks className="size-5" />
          </div>
          <div className="min-w-0">
            <h2 className="eh-h3">{t("modules.intro")}</h2>
            <p className="eh-small mt-1 max-w-[72ch] text-muted-foreground">
              {t("modules.introDesc")}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {MODULE_CARDS.map(({ key, icon: Icon, status }) => (
          <Card key={key}>
            <CardHeader>
              <CardTitle className="eh-h3">
                {t(`modules.cards.${key}.title`)}
              </CardTitle>
              <CardDescription className="min-h-10">
                {t(`modules.cards.${key}.description`)}
              </CardDescription>
              <CardAction>
                <Badge
                  variant="outline"
                  className="font-normal text-muted-foreground"
                >
                  {t(`modules.status.${status}`)}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-3">
              <span
                className="flex size-8 items-center justify-center rounded-lg bg-subtle text-muted-foreground"
                aria-hidden="true"
              >
                <Icon className="size-4" />
              </span>
              <Button variant="outline" size="sm" disabled>
                {t("modules.install")}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

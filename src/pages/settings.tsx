import { useTranslation } from "react-i18next";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { cn } from "cn";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import { APP_LICENSE, APP_VERSION } from "@/lib/app-info";
import { changeLocale } from "@/lib/i18n";
import { PALETTE_PREVIEWS } from "@/lib/palettes";
import { PALETTES, useAppTheme, type PaletteId, type ThemeMode } from "@/lib/theme";

const MODES: { mode: ThemeMode; icon: typeof Sun }[] = [
  { mode: "light", icon: Sun },
  { mode: "dark", icon: Moon },
  { mode: "system", icon: Monitor },
];

function choiceClass(active: boolean) {
  return cn(
    "flex items-center gap-2 rounded-lg border px-3 text-sm transition-colors",
    active
      ? "border-primary bg-accent-soft font-medium text-foreground"
      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { mode, palette, setMode, setPalette } = useAppTheme();
  const currentLocale = i18n.language.startsWith("en") ? "en-US" : "zh-CN";

  return (
    <>
      <PageHeader
        eyebrow={t("settings.eyebrow")}
        title={t("settings.title")}
        description={t("settings.description")}
      />

      <div className="eh-grid">
        <Card className="desk:col-span-8 xl:col-span-12">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("settings.appearance.title")}
            </CardTitle>
            <CardDescription>
              {t("settings.appearance.description")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <section>
              <h3 className="eh-caption mb-2 text-muted-foreground">
                {t("settings.appearance.mode")}
              </h3>
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label={t("settings.appearance.mode")}
              >
                {MODES.map(({ mode: option, icon: Icon }) => (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={mode === option}
                    aria-label={t("a11y.themeOption", {
                      name: t(`themeMode.${option}`),
                    })}
                    className={cn(choiceClass(mode === option), "h-9")}
                    onClick={() => setMode(option)}
                  >
                    <Icon className="size-4" aria-hidden="true" />
                    {t(`themeMode.${option}`)}
                  </button>
                ))}
              </div>
            </section>

            <section>
              <h3 className="eh-caption mb-2 text-muted-foreground">
                {t("settings.appearance.palette")}
              </h3>
              <div className="grid gap-3 sm:grid-cols-3">
                {PALETTES.map((id: PaletteId) => {
                  const active = palette === id;
                  const name = t(`palette.${id}.name`);
                  return (
                    <button
                      key={id}
                      type="button"
                      aria-pressed={active}
                      aria-label={t("a11y.paletteOption", { name })}
                      onClick={() => setPalette(id)}
                      className={cn(
                        "rounded-xl border p-4 text-left transition-colors",
                        active
                          ? "border-primary bg-accent-soft"
                          : "border-border hover:bg-accent",
                      )}
                    >
                      <span className="flex -space-x-1.5" aria-hidden="true">
                        {PALETTE_PREVIEWS[id].map((color) => (
                          <span
                            key={color}
                            className="size-6 rounded-full ring-2 ring-card"
                            style={{ backgroundColor: color }}
                          />
                        ))}
                      </span>
                      <span className="mt-3 flex items-center gap-1.5 text-sm font-medium">
                        {name}
                        {active ? (
                          <Check
                            className="size-3.5 text-primary"
                            aria-hidden="true"
                          />
                        ) : null}
                      </span>
                      <span className="eh-caption mt-0.5 block text-muted-foreground">
                        {t(`palette.${id}.description`)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          </CardContent>
        </Card>

        <Card className="desk:col-span-4 xl:col-span-6">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("settings.language.title")}
            </CardTitle>
            <CardDescription>
              {t("settings.language.description")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label={t("settings.language.title")}
            >
              <button
                type="button"
                aria-pressed={currentLocale === "zh-CN"}
                className={cn(choiceClass(currentLocale === "zh-CN"), "h-9")}
                onClick={() => changeLocale("zh-CN")}
              >
                {t("settings.language.zh")}
              </button>
              <button
                type="button"
                aria-pressed={currentLocale === "en-US"}
                className={cn(choiceClass(currentLocale === "en-US"), "h-9")}
                onClick={() => changeLocale("en-US")}
              >
                {t("settings.language.en")}
              </button>
            </div>
          </CardContent>
        </Card>

        <Card className="desk:col-span-4 xl:col-span-6">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("settings.about.title")}
            </CardTitle>
            <CardDescription>{t("app.tagline")}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">
                  {t("settings.about.version")}
                </dt>
                <dd className="eh-num">{APP_VERSION}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">
                  {t("settings.about.license")}
                </dt>
                <dd>{APP_LICENSE}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">
                  {t("settings.about.storage")}
                </dt>
                <dd>{t("settings.about.storageValue")}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

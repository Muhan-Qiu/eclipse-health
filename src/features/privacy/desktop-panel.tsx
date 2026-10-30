import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cn } from "cn";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { fetchSettings, updateSettings, type SettingsPatch } from "./api";
import {
  applyDesktopPreference,
  isTauriRuntime,
  readLocalPreference,
  type DesktopPreference,
} from "./desktop-preferences";
import {
  analysisNotificationsEnabled,
  setAnalysisNotificationsEnabled,
} from "@/features/profile/notifications";

interface DesktopPanelProps {
  className?: string;
}

const PREFERENCES: DesktopPreference[] = ["closeToTray", "splashEnabled"];

export function DesktopPanel({ className }: DesktopPanelProps) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<DesktopPreference, boolean>>({
    closeToTray: readLocalPreference("closeToTray", true),
    splashEnabled: readLocalPreference("splashEnabled", true),
  });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState<DesktopPreference | null>(null);
  const [notifyOnComplete, setNotifyOnComplete] = useState(() =>
    analysisNotificationsEnabled(),
  );
  const tauri = isTauriRuntime();

  useEffect(() => {
    let active = true;
    fetchSettings()
      .then((settings) => {
        if (!active) return;
        setValues({
          closeToTray: settings.closeToTray,
          splashEnabled: settings.splashEnabled,
        });
      })
      .catch(() => {
        // 后端不可用时保留 localStorage 值，仍可在桌面运行时生效。
      })
      .finally(() => {
        if (active) setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleToggle(preference: DesktopPreference, enabled: boolean) {
    setValues((current) => ({ ...current, [preference]: enabled }));
    setSaving(preference);
    const desktop = await applyDesktopPreference(preference, enabled);
    const patch: SettingsPatch =
      preference === "closeToTray"
        ? { closeToTray: enabled }
        : { splashEnabled: enabled };
    try {
      await updateSettings(patch);
      toast.success(
        desktop === "fallback" ? t("settings.desktop.savedRestart") : t("settings.desktop.saved"),
      );
    } catch (error) {
      toast.error(t("settings.desktop.saveFailed"), {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setSaving(null);
    }
  }

  function handleNotifyToggle(enabled: boolean) {
    setNotifyOnComplete(enabled);
    setAnalysisNotificationsEnabled(enabled);
  }

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("settings.desktop.title")}</CardTitle>
        <CardDescription>{t("settings.desktop.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {PREFERENCES.map((preference) => {
          const labelKey =
            preference === "closeToTray"
              ? "settings.desktop.closeToTray"
              : "settings.desktop.splash";
          const descKey =
            preference === "closeToTray"
              ? "settings.desktop.closeToTrayDesc"
              : "settings.desktop.splashDesc";
          return (
            <div key={preference} className="flex items-start justify-between gap-3">
              <div>
                <Label htmlFor={`desktop-${preference}`}>{t(labelKey)}</Label>
                <p className="eh-caption text-muted-foreground">{t(descKey)}</p>
              </div>
              <Switch
                id={`desktop-${preference}`}
                checked={values[preference]}
                disabled={!loaded || saving === preference}
                onCheckedChange={(checked) => void handleToggle(preference, checked)}
                aria-label={t(labelKey)}
              />
            </div>
          );
        })}
        <div className="flex items-start justify-between gap-3">
          <div>
            <Label htmlFor="desktop-analysis-notifications">
              {t("settings.desktop.notifications")}
            </Label>
            <p className="eh-caption text-muted-foreground">
              {t("settings.desktop.notificationsDesc")}
            </p>
          </div>
          <Switch
            id="desktop-analysis-notifications"
            checked={notifyOnComplete}
            onCheckedChange={handleNotifyToggle}
            aria-label={t("settings.desktop.notifications")}
          />
        </div>
        {!tauri ? (
          <p className="eh-caption text-muted-foreground">
            {t("settings.desktop.browserHint")}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

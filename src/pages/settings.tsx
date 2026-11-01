import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  CloudDownload,
  Loader2,
  Monitor,
  Moon,
  RefreshCw,
  Sun,
} from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { DiagnosticsPanel } from "@/features/export/diagnostics-panel";
import { ExportPanel } from "@/features/export/export-panel";
import { ExternalAccessPanel } from "@/features/external-access/external-access-panel";
import { DesktopPanel } from "@/features/privacy/desktop-panel";
import { PrivacyPanel } from "@/features/privacy/privacy-panel";
import { APP_LICENSE, APP_VERSION } from "@/lib/app-info";
import { baseUrl as apiBaseUrl } from "@/lib/api/client";
import { ApiError, errorMessage } from "@/lib/api/error";
import { formatDateTime } from "@/lib/format";
import { changeLocale, intlLocale } from "@/lib/i18n";
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

const OHS_API = `${apiBaseUrl}/ohs`;

interface OhsWarning {
  code: string;
  message: string;
}

interface OhsLastSync {
  created: number;
  skipped: number;
  failed: number;
  syncedAt?: string;
  warnings?: OhsWarning[];
}

interface OhsSettings {
  configured: boolean;
  baseUrl: string;
  hasToken: boolean;
  userId: string | null;
  lastSync: OhsLastSync | null;
}

interface OhsTestResult {
  ok: boolean;
  baseUrl: string;
  authType: "tenant" | "user" | string;
  userCount: number;
  warnings: OhsWarning[];
}

interface OhsSyncResult {
  created: number;
  skipped: number;
  failed: number;
  warnings: OhsWarning[];
}

async function ohsRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  let response: Response;
  try {
    response = await fetch(`${OHS_API}${path}`, {
      ...init,
      credentials: "omit",
      headers: { Accept: "application/json", ...init.headers },
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时", { code: "timeout", cause: error });
    }
    throw new ApiError("无法连接本地后端", {
      code: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      if (typeof body.code === "string") code = body.code;
      if (typeof body.message === "string") message = body.message;
    } catch {
      // 非 JSON 错误体保留通用文案。
    }
    throw new ApiError(message, { status: response.status, code });
  }
  return (await response.json()) as T;
}

function OhsWarningList({ warnings }: { warnings: OhsWarning[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) {
    return (
      <p className="eh-caption text-muted-foreground">
        {t("settings.ohs.noWarnings")}
      </p>
    );
  }
  return (
    <ul className="space-y-1">
      {warnings.map((warning, index) => (
        <li key={`${warning.code}-${index}`} className="text-sm text-muted-foreground">
          <code className="eh-caption rounded bg-muted px-1 py-0.5">
            {warning.code}
          </code>{" "}
          {warning.message}
        </li>
      ))}
    </ul>
  );
}

function OhsPanel({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [state, setState] = useState<OhsSettings | "loading" | "unavailable">(
    "loading",
  );
  const [base, setBase] = useState("http://127.0.0.1:8080");
  const [token, setToken] = useState("");
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState<"save" | "test" | "sync" | null>(null);
  const [testResult, setTestResult] = useState<OhsTestResult | null>(null);
  const [syncResult, setSyncResult] = useState<OhsSyncResult | null>(null);

  useEffect(() => {
    let active = true;
    ohsRequest<OhsSettings>("/settings")
      .then((settings) => {
        if (!active) return;
        setState(settings);
        setBase(settings.baseUrl);
        setUserId(settings.userId ?? "");
      })
      .catch(() => {
        if (active) setState("unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = base.trim();
    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        throw new Error("invalid protocol");
      }
    } catch {
      toast.error(t("settings.ohs.saveFailed"), {
        description: t("settings.ohs.baseUrlInvalid"),
      });
      return;
    }
    setBusy("save");
    try {
      const saved = await ohsRequest<OhsSettings>("/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseUrl: trimmed,
          token: token.trim() || null,
          userId: userId.trim() || null,
        }),
      });
      setState(saved);
      setBase(saved.baseUrl);
      setUserId(saved.userId ?? "");
      setToken("");
      setTestResult(null);
      toast.success(t("settings.ohs.saved"));
    } catch (error) {
      toast.error(t("settings.ohs.saveFailed"), {
        description: errorMessage(error),
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleTest() {
    setBusy("test");
    setTestResult(null);
    try {
      const result = await ohsRequest<OhsTestResult>("/test", { method: "POST" });
      setTestResult(result);
      toast.success(t("settings.ohs.testOk"));
    } catch (error) {
      toast.error(t("settings.ohs.testFailed"), {
        description: errorMessage(error),
      });
    } finally {
      setBusy(null);
    }
  }

  async function handleSync() {
    setBusy("sync");
    setSyncResult(null);
    try {
      const result = await ohsRequest<OhsSyncResult>("/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days: 30 }),
      });
      setSyncResult(result);
      toast.success(
        t("settings.ohs.syncDone", {
          created: result.created,
          skipped: result.skipped,
          failed: result.failed,
        }),
      );
      try {
        const refreshed = await ohsRequest<OhsSettings>("/settings");
        setState(refreshed);
      } catch {
        // 同步已成功；刷新摘要失败不影响结果展示。
      }
    } catch (error) {
      toast.error(t("settings.ohs.syncFailed"), {
        description: errorMessage(error),
      });
    } finally {
      setBusy(null);
    }
  }

  const title = (
    <CardTitle className="eh-h3">{t("settings.ohs.title")}</CardTitle>
  );

  if (state === "loading") {
    return (
      <Card className={cn(className)}>
        <CardHeader>{title}</CardHeader>
        <CardContent>
          <p className="eh-caption text-muted-foreground">
            {t("settings.ohs.loading")}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (state === "unavailable") {
    return (
      <Card className={cn(className)}>
        <CardHeader>
          {title}
          <CardDescription>{t("settings.ohs.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <p className="text-sm font-medium">
              {t("settings.ohs.unavailableTitle")}
            </p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("settings.ohs.unavailableDesc")}
            </p>
          </div>
          <p className="eh-caption text-muted-foreground">
            {t("settings.ohs.docsHint")}
          </p>
        </CardContent>
      </Card>
    );
  }

  const settings = state;
  const lastSync: OhsLastSync | null = syncResult
    ? {
        ...(settings.lastSync ?? { created: 0, skipped: 0, failed: 0 }),
        ...syncResult,
      }
    : settings.lastSync;
  const warnings = testResult?.warnings ?? lastSync?.warnings ?? [];
  const disabled = busy !== null;

  return (
    <Card className={cn(className)}>
      <CardHeader>
        {title}
        <CardDescription>{t("settings.ohs.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-lg border border-border bg-muted/40 p-3">
          <p className="text-sm">{t("settings.ohs.requirement")}</p>
        </div>

        <form className="space-y-4" onSubmit={(event) => void handleSave(event)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ohs-base-url">
                {t("settings.ohs.baseUrlLabel")}
              </Label>
              <Input
                id="ohs-base-url"
                value={base}
                placeholder={t("settings.ohs.baseUrlPlaceholder")}
                autoComplete="off"
                spellCheck={false}
                disabled={disabled}
                onChange={(event) => setBase(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ohs-user-id">
                {t("settings.ohs.userIdLabel")}
              </Label>
              <Input
                id="ohs-user-id"
                value={userId}
                placeholder={t("settings.ohs.userIdPlaceholder")}
                autoComplete="off"
                spellCheck={false}
                disabled={disabled}
                onChange={(event) => setUserId(event.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ohs-token">{t("settings.ohs.tokenLabel")}</Label>
            <Input
              id="ohs-token"
              type="password"
              value={token}
              placeholder={
                settings.hasToken
                  ? t("settings.ohs.tokenStoredPlaceholder")
                  : t("settings.ohs.tokenPlaceholder")
              }
              autoComplete="new-password"
              disabled={disabled}
              onChange={(event) => setToken(event.target.value)}
            />
            <p className="eh-caption text-muted-foreground">
              {t("settings.ohs.tokenHint")}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={disabled}>
              {busy === "save" ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : null}
              {busy === "save"
                ? t("settings.ohs.saving")
                : t("settings.ohs.save")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled || !settings.configured}
              onClick={() => void handleTest()}
            >
              {busy === "test" ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw aria-hidden="true" />
              )}
              {busy === "test"
                ? t("settings.ohs.testing")
                : t("settings.ohs.test")}
            </Button>
            {settings.configured ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={disabled}
                onClick={() => void handleSync()}
              >
                {busy === "sync" ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <CloudDownload aria-hidden="true" />
                )}
                {busy === "sync"
                  ? t("settings.ohs.syncing")
                  : t("settings.ohs.sync")}
              </Button>
            ) : null}
          </div>
          <p className="eh-caption text-muted-foreground">
            {settings.configured
              ? t("settings.ohs.unsavedHint")
              : t("settings.ohs.notConfigured")}
          </p>
        </form>

        {testResult ? (
          <div className="rounded-lg border border-border p-3">
            <p className="text-sm font-medium">
              {t("settings.ohs.testOk")} ·{" "}
              {testResult.authType === "tenant"
                ? t("settings.ohs.testTenant", { n: testResult.userCount })
                : t("settings.ohs.testUser", { n: testResult.userCount })}
            </p>
            <div className="mt-2">
              <OhsWarningList warnings={testResult.warnings} />
            </div>
          </div>
        ) : null}

        {lastSync ? (
          <div className="rounded-lg border border-border p-3">
            <p className="eh-caption text-muted-foreground">
              {lastSync.syncedAt
                ? t("settings.ohs.lastSync", {
                    time: formatDateTime(lastSync.syncedAt, locale),
                    created: lastSync.created,
                    skipped: lastSync.skipped,
                    failed: lastSync.failed,
                  })
                : t("settings.ohs.neverSynced")}
            </p>
            <div className="mt-2">
              <OhsWarningList warnings={lastSync.warnings ?? []} />
            </div>
          </div>
        ) : null}

        {!lastSync && warnings.length === 0 ? (
          <p className="eh-caption text-muted-foreground">
            {t("settings.ohs.syncHint")}
          </p>
        ) : null}

        <section className="space-y-2">
          <h3 className="eh-caption text-muted-foreground">
            {t("settings.ohs.exampleTitle")}
          </h3>
          <pre className="overflow-x-auto rounded-md bg-muted px-2.5 py-2 font-mono text-[0.7rem] leading-relaxed">
            {`curl -H "Authorization: Bearer ****" \\\n  ${base.replace(/\/+$/, "")}/v1/users`}
          </pre>
          <p className="eh-caption text-muted-foreground">
            {t("settings.ohs.docsHint")}
          </p>
        </section>
      </CardContent>
    </Card>
  );
}


export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { mode, palette, setMode, setPalette } = useAppTheme();
  const currentLocale = i18n.language.startsWith("en") ? "en-US" : "zh-CN";
  const [dataVersion, setDataVersion] = useState(0);

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

        <Card className="desk:col-span-8 xl:col-span-4">
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

        <ExportPanel
          className="desk:col-span-8 xl:col-span-8"
          onDataChanged={() => setDataVersion((value) => value + 1)}
        />

        <PrivacyPanel
          className="desk:col-span-4 xl:col-span-6"
          refreshSignal={dataVersion}
          onPurged={() => setDataVersion((value) => value + 1)}
        />

        <DesktopPanel className="desk:col-span-4 xl:col-span-6" />

        <ExternalAccessPanel className="desk:col-span-8 xl:col-span-6" />

        <OhsPanel className="desk:col-span-8 xl:col-span-6" />

        <DiagnosticsPanel className="desk:col-span-4 xl:col-span-6" />

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

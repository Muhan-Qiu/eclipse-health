import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CircleAlert,
  CircleCheck,
  KeyRound,
  LoaderCircle,
  Plus,
  Server,
  Trash2,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "cn";
import { errorMessage } from "@/lib/api/error";
import { assistantApi } from "./api";
import type {
  AssistantProvider,
  ProviderInput,
  ProviderKind,
  ProviderTestResult,
} from "./types";

const KIND_ORDER: ProviderKind[] = ["mock", "ollama", "openai", "anthropic"];

const DEFAULT_MODEL: Record<ProviderKind, string> = {
  mock: "mock-1",
  ollama: "llama3.1",
  openai: "gpt-4.1-mini",
  anthropic: "claude-sonnet-5",
};

const DEFAULT_BASE_URL: Record<ProviderKind, string> = {
  mock: "",
  ollama: "http://127.0.0.1:11434",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
};

const NEEDS_KEY: Record<ProviderKind, boolean> = {
  mock: false,
  ollama: false,
  openai: true,
  anthropic: true,
};

interface ProviderPreset {
  label: string;
  model: string;
  baseUrl: string;
}

/**
 * DeepSeek / OpenCode 通过 CC Switch 这类本地代理暴露 Anthropic Messages 格式。
 * 只预填地址与占位模型名，不预填任何真实 Key。
 */
const PROXY_PRESET: ProviderPreset = {
  label: "DeepSeek / OpenCode",
  model: "deepseek-chat",
  baseUrl: "http://127.0.0.1:15721",
};

interface Draft {
  kind: ProviderKind;
  label: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  clearKey: boolean;
  enabled: boolean;
}

function draftFrom(
  provider: AssistantProvider | null,
  initialKind: ProviderKind = "mock",
  preset: ProviderPreset | null = null,
): Draft {
  if (!provider) {
    return {
      kind: initialKind,
      label: preset?.label ?? "",
      model: preset?.model ?? DEFAULT_MODEL[initialKind],
      baseUrl: preset?.baseUrl ?? DEFAULT_BASE_URL[initialKind],
      apiKey: "",
      clearKey: false,
      enabled: true,
    };
  }
  return {
    kind: provider.kind,
    label: provider.label,
    model: provider.model,
    baseUrl: provider.baseUrl ?? "",
    apiKey: "",
    clearKey: false,
    enabled: provider.enabled,
  };
}

function newProviderId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `llm_${crypto.randomUUID()}`;
  }
  return `llm_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

interface ProviderFormProps {
  provider: AssistantProvider | null;
  initialKind?: ProviderKind;
  preset?: ProviderPreset | null;
  autoFocusLabel?: boolean;
  onSaved: (provider: AssistantProvider) => Promise<void> | void;
  onDeleted?: (id: string) => Promise<void> | void;
  onCancel?: () => void;
  onError: (message: string) => void;
}

function ProviderForm({
  provider,
  initialKind = "mock",
  preset = null,
  autoFocusLabel = false,
  onSaved,
  onDeleted,
  onCancel,
  onError,
}: ProviderFormProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Draft>(() =>
    draftFrom(provider, initialKind, preset),
  );
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
    result: ProviderTestResult | null;
  } | null>(null);

  const isNew = provider === null;
  const needsKey = NEEDS_KEY[draft.kind];

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setTestResult(null);
  };

  const changeKind = (kind: ProviderKind) => {
    setDraft((current) => ({
      ...current,
      kind,
      model: DEFAULT_MODEL[kind],
      baseUrl: DEFAULT_BASE_URL[kind],
      apiKey: "",
      clearKey: false,
    }));
    setTestResult(null);
  };

  const save = async () => {
    setSaving(true);
    try {
      const input: ProviderInput = {
        kind: draft.kind,
        label: draft.label.trim() || t(`assistant.providers.kinds.${draft.kind}`),
        model: draft.model.trim() || DEFAULT_MODEL[draft.kind],
        baseUrl: draft.kind === "mock" ? null : draft.baseUrl.trim() || null,
        enabled: draft.enabled,
      };
      if (draft.clearKey) input.clearKey = true;
      else if (draft.apiKey.trim()) input.apiKey = draft.apiKey.trim();
      const saved = await assistantApi.providers.save(
        provider?.id ?? newProviderId(),
        input,
      );
      setDraft((current) => ({ ...current, apiKey: "", clearKey: false }));
      setTestResult(null);
      await onSaved(saved);
    } catch (cause) {
      onError(`${t("assistant.providers.error")}：${errorMessage(cause)}`);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!provider) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await assistantApi.providers.test(provider.id);
      setTestResult({
        ok: result.ok,
        message: result.ok
          ? t("assistant.providers.testOkMessage", { ms: result.latencyMs ?? 0 })
          : t("assistant.providers.testFailMessage", { message: result.message }),
        result,
      });
    } catch (cause) {
      setTestResult({
        ok: false,
        message: t("assistant.providers.testFailMessage", {
          message: errorMessage(cause),
        }),
        result: null,
      });
    } finally {
      setTesting(false);
    }
  };

  const remove = async () => {
    if (!provider || !onDeleted) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    await onDeleted(provider.id);
  };

  return (
    <div className="space-y-3 rounded-xl border border-border bg-surface/50 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="assistant-provider-kind">
            {t("assistant.providers.kind")}
          </Label>
          <Select value={draft.kind} onValueChange={(value) => changeKind(value as ProviderKind)}>
            <SelectTrigger id="assistant-provider-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KIND_ORDER.map((kind) => (
                <SelectItem key={kind} value={kind}>
                  {t(`assistant.providers.kinds.${kind}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="assistant-provider-label">
            {t("assistant.providers.label")}
          </Label>
          <Input
            id="assistant-provider-label"
            autoFocus={autoFocusLabel}
            value={draft.label}
            placeholder={t(`assistant.providers.kinds.${draft.kind}`)}
            onChange={(event) => update("label", event.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="assistant-provider-model">
          {t("assistant.providers.model")}
        </Label>
        <Input
          id="assistant-provider-model"
          value={draft.model}
          onChange={(event) => update("model", event.target.value)}
        />
      </div>

      {draft.kind !== "mock" ? (
        <div className="grid gap-1.5">
          <Label htmlFor="assistant-provider-base">
            {t("assistant.providers.baseUrl")}
          </Label>
          <Input
            id="assistant-provider-base"
            value={draft.baseUrl}
            placeholder={t("assistant.providers.baseUrlPlaceholder")}
            onChange={(event) => update("baseUrl", event.target.value)}
          />
          {preset && draft.kind === "anthropic" ? (
            <p className="eh-caption text-muted-foreground">
              {t("assistant.providers.proxyHint")}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="eh-caption text-muted-foreground">
          {t("assistant.providers.mockHint")}
        </p>
      )}

      {needsKey ? (
        <div className="grid gap-1.5">
          <Label htmlFor="assistant-provider-key">
            {t("assistant.providers.apiKey")}
          </Label>
          <div className="flex items-center gap-2">
            <Input
              id="assistant-provider-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft.apiKey}
              placeholder={
                provider?.configured
                  ? t("assistant.providers.apiKeyPlaceholderConfigured")
                  : t("assistant.providers.apiKeyPlaceholder")
              }
              onChange={(event) => update("apiKey", event.target.value)}
            />
            {provider?.configured ? (
              <Button
                type="button"
                variant={draft.clearKey ? "destructive" : "outline"}
                size="sm"
                onClick={() => update("clearKey", !draft.clearKey)}
              >
                <KeyRound data-icon="inline-start" />
                {t("assistant.providers.apiKeyClear")}
              </Button>
            ) : null}
          </div>
          <p className="eh-caption text-muted-foreground">
            {t("assistant.providers.apiKeyHint")}
          </p>
        </div>
      ) : null}

      {needsKey && !provider?.configured ? (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-subtle px-3 py-2 text-xs">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span>{t("assistant.providers.missingKeyNotice")}</span>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-2">
        <Label htmlFor="assistant-provider-enabled" className="text-sm">
          {t("assistant.providers.enabled")}
        </Label>
        <Switch
          id="assistant-provider-enabled"
          checked={draft.enabled}
          onCheckedChange={(checked) => update("enabled", checked)}
        />
      </div>

      {testResult ? (
        <div
          className={cn(
            "rounded-lg border px-3 py-2 text-sm",
            testResult.ok
              ? "border-border bg-subtle text-foreground"
              : "border-destructive/40 bg-destructive/5 text-destructive",
          )}
          role="status"
        >
          <div className="flex items-start gap-2">
            {testResult.ok ? (
              <CircleCheck className="mt-0.5 size-4" aria-hidden="true" />
            ) : (
              <CircleAlert className="mt-0.5 size-4" aria-hidden="true" />
            )}
            <span>{testResult.message}</span>
          </div>
          {testResult.result ? (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {testResult.result.latencyMs !== null ? (
                <Badge variant="secondary" className="font-normal">
                  {t("assistant.providers.latency", { ms: testResult.result.latencyMs })}
                </Badge>
              ) : null}
              {testResult.result.available === true ? (
                <Badge variant="outline" className="font-normal">
                  {t("assistant.providers.modelAvailable")}
                </Badge>
              ) : testResult.result.available === false ? (
                <Badge
                  variant="outline"
                  className="border-destructive/40 font-normal text-destructive"
                >
                  {t("assistant.providers.modelMissing")}
                </Badge>
              ) : null}
              {testResult.result.supportsTools === true ? (
                <Badge variant="outline" className="font-normal">
                  {t("assistant.providers.toolsSupported")}
                </Badge>
              ) : testResult.result.supportsTools === false ? (
                <Badge variant="outline" className="font-normal text-muted-foreground">
                  {t("assistant.providers.toolsUnsupported")}
                </Badge>
              ) : (
                <Badge variant="outline" className="font-normal text-muted-foreground">
                  {t("assistant.providers.toolsUnknown")}
                </Badge>
              )}
            </div>
          ) : null}
          {testResult.result?.models.length ? (
            <p className="eh-caption mt-1.5 text-muted-foreground">
              {t("assistant.providers.availableModels", {
                models: testResult.result.models.slice(0, 6).join("、"),
              })}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => void save()} disabled={saving}>
          {saving ? <LoaderCircle className="animate-spin" data-icon="inline-start" /> : null}
          {saving ? t("assistant.providers.saving") : t("assistant.providers.save")}
        </Button>
        {provider ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void test()}
            disabled={testing}
          >
            {testing ? (
              <LoaderCircle className="animate-spin" data-icon="inline-start" />
            ) : (
              <Wrench data-icon="inline-start" />
            )}
            {testing ? t("assistant.providers.testing") : t("assistant.providers.test")}
          </Button>
        ) : null}
        {provider && onDeleted ? (
          <Button
            size="sm"
            variant={confirmDelete ? "destructive" : "ghost"}
            onClick={() => void remove()}
          >
            <Trash2 data-icon="inline-start" />
            {confirmDelete
              ? t("assistant.providers.deleteConfirm")
              : t("assistant.providers.delete")}
          </Button>
        ) : null}
        {isNew && onCancel ? (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            {t("assistant.privacy.cancel")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export interface ProviderCardProps {
  providers: AssistantProvider[];
  activeId: string | null;
  onActiveChange: (id: string) => void;
  onProvidersChanged: () => Promise<void>;
  onError: (message: string) => void;
}

export function ProviderCard({
  providers,
  activeId,
  onActiveChange,
  onProvidersChanged,
  onError,
}: ProviderCardProps) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState<{
    kind: ProviderKind;
    preset: ProviderPreset | null;
  } | null>(null);
  const isCreating = creating !== null;
  const selected = providers.find((provider) => provider.id === activeId) ?? null;

  const saved = async (provider: AssistantProvider) => {
    await onProvidersChanged();
    onActiveChange(provider.id);
    setCreating(null);
  };

  const deleted = async (id: string) => {
    try {
      await assistantApi.providers.remove(id);
      await onProvidersChanged();
      const next = providers.find((provider) => provider.id !== id);
      if (next) onActiveChange(next.id);
    } catch (cause) {
      onError(`${t("assistant.providers.error")}：${errorMessage(cause)}`);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="eh-h3">{t("assistant.providers.title")}</CardTitle>
        <CardDescription>{t("assistant.providers.description")}</CardDescription>
        <CardAction>
          {!isCreating ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCreating({ kind: "anthropic", preset: PROXY_PRESET })}
              >
                <KeyRound data-icon="inline-start" />
                {t("assistant.providers.proxyQuickShort")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setCreating({ kind: "mock", preset: null })}>
                <Plus data-icon="inline-start" />
                {t("assistant.providers.add")}
              </Button>
            </div>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {providers.length === 0 && !isCreating ? (
          <div className="space-y-3 rounded-xl border border-dashed border-border bg-surface/40 p-4">
            <div className="space-y-1">
              <p className="eh-small font-medium">{t("assistant.providers.emptyTitle")}</p>
              <p className="eh-caption text-muted-foreground">
                {t("assistant.providers.emptyDesc")}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setCreating({ kind: "mock", preset: null })}>
                <Server data-icon="inline-start" />
                {t("assistant.providers.mockQuick")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCreating({ kind: "ollama", preset: null })}
              >
                <Server data-icon="inline-start" />
                {t("assistant.providers.ollamaQuick")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCreating({ kind: "openai", preset: null })}
              >
                <KeyRound data-icon="inline-start" />
                {t("assistant.providers.apiQuick")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCreating({ kind: "anthropic", preset: PROXY_PRESET })}
              >
                <KeyRound data-icon="inline-start" />
                {t("assistant.providers.proxyQuick")}
              </Button>
            </div>
          </div>
        ) : null}

        {providers.length > 0 ? (
          <div className="space-y-1.5">
            {providers.map((provider) => {
              const isActive = provider.id === selected?.id && !isCreating;
              return (
                <button
                  key={provider.id}
                  type="button"
                  onClick={() => {
                    setCreating(null);
                    onActiveChange(provider.id);
                  }}
                  aria-pressed={isActive}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                    isActive
                      ? "border-primary/40 bg-accent-soft"
                      : "border-border bg-background hover:bg-muted/60",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {provider.label}
                    </span>
                    <span className="eh-caption block truncate text-muted-foreground">
                      {t(`assistant.providers.kinds.${provider.kind}`)} · {provider.model}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {provider.isLocal ? (
                      <Badge variant="secondary" className="font-normal">
                        {t("assistant.providers.localBadge")}
                      </Badge>
                    ) : null}
                    {provider.kind !== "mock" && !provider.isLocal ? (
                      <Badge
                        variant="outline"
                        className="font-normal text-muted-foreground"
                      >
                        {provider.configured
                          ? t("assistant.providers.configuredBadge")
                          : t("assistant.providers.noKeyBadge")}
                      </Badge>
                    ) : null}
                    {!provider.enabled ? (
                      <Badge variant="outline" className="font-normal text-muted-foreground">
                        {t("assistant.providers.disabledBadge")}
                      </Badge>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}

        {creating !== null ? (
          <ProviderForm
            key={`${creating.kind}:${creating.preset ? "preset" : "blank"}`}
            provider={null}
            initialKind={creating.kind}
            preset={creating.preset}
            autoFocusLabel
            onSaved={saved}
            onCancel={() => setCreating(null)}
            onError={onError}
          />
        ) : selected ? (
          <ProviderForm
            key={selected.id}
            provider={selected}
            onSaved={saved}
            onDeleted={deleted}
            onError={onError}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

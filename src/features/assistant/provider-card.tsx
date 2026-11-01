import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  CircleAlert,
  CircleCheck,
  ExternalLink,
  KeyRound,
  LoaderCircle,
  Plus,
  Search,
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
  ProviderPreset,
  ProviderPresetGroup,
  ProviderTestResult,
} from "./types";

const LEGACY_KINDS: ProviderKind[] = ["mock", "ollama", "openai", "anthropic"];

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

const GROUP_ORDER: ProviderPresetGroup[] = [
  "official",
  "china",
  "gateway",
  "local",
  "custom",
  "demo",
];

interface Draft {
  presetId: string | null;
  kind: ProviderKind;
  label: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  clearKey: boolean;
  enabled: boolean;
}

function draftFromPreset(preset: ProviderPreset): Draft {
  return {
    presetId: preset.id,
    kind: preset.kind,
    label: preset.label,
    model: preset.defaultModel,
    baseUrl: preset.baseUrl ?? "",
    apiKey: "",
    clearKey: false,
    enabled: true,
  };
}

function draftFromProvider(provider: AssistantProvider): Draft {
  return {
    presetId: provider.presetId,
    kind: provider.kind,
    label: provider.label,
    model: provider.model,
    baseUrl: provider.baseUrl ?? "",
    apiKey: "",
    clearKey: false,
    enabled: provider.enabled,
  };
}

function draftFromLegacy(initialKind: ProviderKind): Draft {
  return {
    presetId: null,
    kind: initialKind,
    label: "",
    model: DEFAULT_MODEL[initialKind],
    baseUrl: DEFAULT_BASE_URL[initialKind],
    apiKey: "",
    clearKey: false,
    enabled: true,
  };
}

function newProviderId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `llm_${crypto.randomUUID()}`;
  }
  return `llm_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function localizedPreset(
  preset: ProviderPreset,
  english: boolean,
): { label: string; description: string } {
  return {
    label: english ? preset.labelEn : preset.label,
    description: english ? preset.descriptionEn : preset.description,
  };
}

function presetForProvider(
  provider: AssistantProvider | null,
  presetsById: Map<string, ProviderPreset>,
): ProviderPreset | null {
  if (!provider?.presetId) return null;
  return presetsById.get(provider.presetId) ?? null;
}

function presetBadgeLabel(
  provider: AssistantProvider,
  presetsById: Map<string, ProviderPreset>,
  english: boolean,
): string {
  const preset = presetForProvider(provider, presetsById);
  return preset
    ? localizedPreset(preset, english).label
    : provider.kind;
}

interface ProviderFormProps {
  provider: AssistantProvider | null;
  preset: ProviderPreset | null;
  presetsById: Map<string, ProviderPreset>;
  autoFocusKey?: boolean;
  onSaved: (provider: AssistantProvider) => Promise<void> | void;
  onDeleted?: (id: string) => Promise<void> | void;
  onCancel?: () => void;
  onError: (message: string) => void;
}

function ProviderForm({
  provider,
  preset,
  presetsById,
  autoFocusKey = false,
  onSaved,
  onDeleted,
  onCancel,
  onError,
}: ProviderFormProps) {
  const { t, i18n } = useTranslation();
  const english = i18n.language.startsWith("en");
  const [draft, setDraft] = useState<Draft>(() =>
    provider ? draftFromProvider(provider) : preset ? draftFromPreset(preset) : draftFromLegacy("mock"),
  );
  const [advancedOpen, setAdvancedOpen] = useState(Boolean(preset?.requiresBaseUrl));
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
    result: ProviderTestResult | null;
  } | null>(null);

  const isNew = provider === null;
  const needsKey =
    preset?.needsKey ?? provider?.needsKey ?? (draft.kind === "openai" || draft.kind === "anthropic");
  const isLocal =
    preset?.local ?? provider?.isLocal ?? (draft.kind === "ollama" || draft.kind === "mock");
  const requiresBaseUrl = preset?.requiresBaseUrl ?? false;
  const presetInfo = preset ? localizedPreset(preset, english) : null;
  const protocol =
    preset?.litellmProvider ?? provider?.litellmProvider ?? (draft.kind === "mock" ? "mock" : draft.kind);
  const baseUrlMissing = requiresBaseUrl && !draft.baseUrl.trim();

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setTestResult(null);
  };

  const changeLegacyKind = (kind: ProviderKind) => {
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
    if (baseUrlMissing) {
      onError(t("assistant.providers.baseUrlRequired"));
      return;
    }
    setSaving(true);
    try {
      const input: ProviderInput = {
        label: draft.label.trim() || preset?.label || t(`assistant.providers.kinds.${draft.kind}`),
        model: draft.model.trim() || preset?.defaultModel || DEFAULT_MODEL[draft.kind],
        baseUrl: draft.kind === "mock" ? null : draft.baseUrl.trim() || null,
        enabled: draft.enabled,
      };
      if (preset) input.presetId = preset.id;
      else input.kind = draft.kind;
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
      {preset && presetInfo ? (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium">{presetInfo.label}</p>
            <p className="eh-caption text-muted-foreground">{presetInfo.description}</p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
            {isLocal ? (
              <Badge variant="secondary" className="font-normal">
                {t("assistant.providers.localBadge")}
              </Badge>
            ) : null}
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {needsKey
                ? t("assistant.providers.needsKeyBadge")
                : t("assistant.providers.noKeyRequiredBadge")}
            </Badge>
            {preset.docsUrl ? (
              <a
                href={preset.docsUrl}
                target="_blank"
                rel="noreferrer"
                className="eh-caption inline-flex items-center gap-1 text-muted-foreground underline-offset-2 hover:underline"
              >
                {t("assistant.providers.docs")}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            ) : null}
          </div>
        </div>
      ) : null}

      {needsKey ? (
        <div className="grid gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="assistant-provider-key">
              {t("assistant.providers.apiKey")}
            </Label>
            {preset?.keyUrl ? (
              <a
                href={preset.keyUrl}
                target="_blank"
                rel="noreferrer"
                className="eh-caption inline-flex items-center gap-1 text-muted-foreground underline-offset-2 hover:underline"
              >
                {t("assistant.providers.applyKey")}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Input
              id="assistant-provider-key"
              type="password"
              autoFocus={autoFocusKey}
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

      {needsKey && !provider?.configured && !draft.apiKey.trim() ? (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-subtle px-3 py-2 text-xs">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span>{t("assistant.providers.missingKeyNotice")}</span>
        </div>
      ) : null}

      <div className="grid gap-1.5">
        <Label htmlFor="assistant-provider-model">
          {t("assistant.providers.model")}
        </Label>
        <Input
          id="assistant-provider-model"
          value={draft.model}
          placeholder={preset?.defaultModel ?? DEFAULT_MODEL[draft.kind]}
          onChange={(event) => update("model", event.target.value)}
        />
        {preset?.models.length ? (
          <div className="flex flex-wrap gap-1.5">
            {preset.models.map((model) => (
              <button
                key={model}
                type="button"
                onClick={() => update("model", model)}
                aria-pressed={draft.model === model}
                className={cn(
                  "rounded-full border px-2 py-0.5 text-xs transition-colors",
                  draft.model === model
                    ? "border-primary/50 bg-accent-soft text-foreground"
                    : "border-border text-muted-foreground hover:bg-muted/60",
                )}
              >
                {model}
              </button>
            ))}
          </div>
        ) : null}
        {preset?.requiresBaseUrl ? (
          <p className="eh-caption text-muted-foreground">
            {t("assistant.providers.modelFreeformHint")}
          </p>
        ) : null}
      </div>

      {preset ? (
        <div className="rounded-lg border border-border/70">
          <button
            type="button"
            onClick={() => setAdvancedOpen((open) => !open)}
            aria-expanded={advancedOpen}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm"
          >
            <span>{t("assistant.providers.advanced")}</span>
            <ChevronDown
              className={cn(
                "size-4 text-muted-foreground transition-transform",
                advancedOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
          {advancedOpen ? (
            <div className="space-y-3 border-t border-border/70 px-3 py-3">
              <div className="grid gap-1.5">
                <Label htmlFor="assistant-provider-label">
                  {t("assistant.providers.label")}
                </Label>
                <Input
                  id="assistant-provider-label"
                  value={draft.label}
                  placeholder={preset.label}
                  onChange={(event) => update("label", event.target.value)}
                />
              </div>
              {draft.kind !== "mock" ? (
                <div className="grid gap-1.5">
                  <Label htmlFor="assistant-provider-base">
                    {t("assistant.providers.baseUrl")}
                    {requiresBaseUrl ? (
                      <span className="text-destructive"> *</span>
                    ) : null}
                  </Label>
                  <Input
                    id="assistant-provider-base"
                    value={draft.baseUrl}
                    placeholder={preset.baseUrl ?? t("assistant.providers.baseUrlPlaceholder")}
                    aria-invalid={baseUrlMissing}
                    onChange={(event) => update("baseUrl", event.target.value)}
                  />
                  <p className="eh-caption text-muted-foreground">
                    {requiresBaseUrl
                      ? t("assistant.providers.baseUrlRequired")
                      : t("assistant.providers.baseUrlHint")}
                  </p>
                </div>
              ) : null}
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm">{t("assistant.providers.protocol")}</p>
                  <p className="eh-caption truncate text-muted-foreground">
                    {protocol}/{draft.model || preset.defaultModel}
                  </p>
                </div>
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{protocol}</code>
              </div>
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="assistant-provider-enabled" className="text-sm">
                  {t("assistant.providers.enabled")}
                </Label>
                <Switch
                  id="assistant-provider-enabled"
                  checked={draft.enabled}
                  onCheckedChange={(checked) => update("enabled", checked)}
                />
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="assistant-provider-kind">
                {t("assistant.providers.kind")}
              </Label>
              <Select
                value={draft.kind}
                onValueChange={(value) => changeLegacyKind(value as ProviderKind)}
              >
                <SelectTrigger id="assistant-provider-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LEGACY_KINDS.map((kind) => (
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
                value={draft.label}
                placeholder={t(`assistant.providers.kinds.${draft.kind}`)}
                onChange={(event) => update("label", event.target.value)}
              />
            </div>
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
            </div>
          ) : (
            <p className="eh-caption text-muted-foreground">
              {t("assistant.providers.mockHint")}
            </p>
          )}

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
        </>
      )}

      {preset && draft.kind === "mock" ? (
        <p className="eh-caption text-muted-foreground">
          {t("assistant.providers.mockHint")}
        </p>
      ) : null}

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
        <Button size="sm" onClick={() => void save()} disabled={saving || baseUrlMissing}>
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
        {preset && provider ? (
          <span className="eh-caption text-muted-foreground">
            {t("assistant.providers.presetApplied", {
              label: presetBadgeLabel(provider, presetsById, english),
            })}
          </span>
        ) : null}
      </div>
    </div>
  );
}

interface PresetPickerProps {
  presets: ProviderPreset[];
  loading: boolean;
  failed: boolean;
  onPick: (preset: ProviderPreset) => void;
  onCancel: () => void;
}

function PresetPicker({ presets, loading, failed, onPick, onCancel }: PresetPickerProps) {
  const { t, i18n } = useTranslation();
  const english = i18n.language.startsWith("en");
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();

  const filtered = useMemo(() => {
    if (!needle) return presets;
    return presets.filter((preset) => {
      const { label, description } = localizedPreset(preset, english);
      return [label, preset.label, preset.labelEn, description, preset.id, preset.litellmProvider]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [presets, needle, english]);

  return (
    <div className="space-y-3 rounded-xl border border-border bg-surface/50 p-3">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("assistant.providers.searchPlaceholder")}
          className="pl-8"
          autoFocus
          aria-label={t("assistant.providers.searchPlaceholder")}
        />
      </div>

      {loading ? (
        <p className="eh-caption flex items-center gap-2 text-muted-foreground">
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
          {t("assistant.providers.loadingPresets")}
        </p>
      ) : failed ? (
        <p className="eh-caption text-destructive">
          {t("assistant.providers.loadPresetsFailed")}
        </p>
      ) : (
        <div className="max-h-96 space-y-4 overflow-y-auto pr-1">
          {GROUP_ORDER.map((group) => {
            const items = filtered.filter((preset) => preset.group === group);
            if (!items.length) return null;
            return (
              <div key={group} className="space-y-1.5">
                <p className="eh-caption font-medium text-muted-foreground">
                  {t(`assistant.providers.groups.${group}`)}
                </p>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {items.map((preset) => {
                    const info = localizedPreset(preset, english);
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => onPick(preset)}
                        className="flex min-h-16 flex-col items-start gap-1 rounded-lg border border-border bg-background px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-muted/60"
                      >
                        <span className="flex w-full items-center justify-between gap-2">
                          <span className="truncate text-sm font-medium">{info.label}</span>
                          {preset.local ? (
                            <Badge variant="secondary" className="shrink-0 font-normal">
                              {t("assistant.providers.localBadge")}
                            </Badge>
                          ) : preset.needsKey ? (
                            <Badge
                              variant="outline"
                              className="shrink-0 font-normal text-muted-foreground"
                            >
                              {t("assistant.providers.needsKeyBadge")}
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="shrink-0 font-normal text-muted-foreground"
                            >
                              {t("assistant.providers.noKeyRequiredBadge")}
                            </Badge>
                          )}
                        </span>
                        <span className="eh-caption line-clamp-2 text-muted-foreground">
                          {info.description}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {!filtered.length ? (
            <p className="eh-caption text-muted-foreground">
              {t("assistant.providers.searchEmpty")}
            </p>
          ) : null}
        </div>
      )}

      <div className="flex justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {t("assistant.privacy.cancel")}
        </Button>
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
  const { t, i18n } = useTranslation();
  const english = i18n.language.startsWith("en");
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [presetsFailed, setPresetsFailed] = useState(false);
  const [picking, setPicking] = useState(false);
  const [creating, setCreating] = useState<ProviderPreset | null>(null);
  const selected = providers.find((provider) => provider.id === activeId) ?? null;

  useEffect(() => {
    let cancelled = false;
    setPresetsLoading(true);
    setPresetsFailed(false);
    assistantApi.providers
      .presets()
      .then((items) => {
        if (cancelled) return;
        setPresets(items);
      })
      .catch(() => {
        if (!cancelled) setPresetsFailed(true);
      })
      .finally(() => {
        if (!cancelled) setPresetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const presetsById = useMemo(
    () => new Map(presets.map((preset) => [preset.id, preset])),
    [presets],
  );
  const quickPreset = (id: string) => presetsById.get(id) ?? null;

  const isCreating = creating !== null;

  const start = (preset: ProviderPreset) => {
    setCreating(preset);
    setPicking(false);
  };

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

  const selectedPreset = presetForProvider(selected, presetsById);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="eh-h3">{t("assistant.providers.title")}</CardTitle>
        <CardDescription>{t("assistant.providers.description")}</CardDescription>
        <CardAction>
          {!isCreating && !picking ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setCreating(null);
                setPicking(true);
              }}
            >
              <Plus data-icon="inline-start" />
              {t("assistant.providers.add")}
            </Button>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {providers.length === 0 && !isCreating && !picking ? (
          <div className="space-y-3 rounded-xl border border-dashed border-border bg-surface/40 p-4">
            <div className="space-y-1">
              <p className="eh-small font-medium">{t("assistant.providers.emptyTitle")}</p>
              <p className="eh-caption text-muted-foreground">
                {t("assistant.providers.emptyDesc")}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {quickPreset("mock") ? (
                <Button size="sm" onClick={() => start(quickPreset("mock")!)}>
                  <Server data-icon="inline-start" />
                  {t("assistant.providers.mockQuick")}
                </Button>
              ) : null}
              {quickPreset("ollama") ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => start(quickPreset("ollama")!)}
                >
                  <Server data-icon="inline-start" />
                  {t("assistant.providers.ollamaQuick")}
                </Button>
              ) : null}
              <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
                <Plus data-icon="inline-start" />
                {t("assistant.providers.browsePresets")}
              </Button>
              {quickPreset("custom-openai") ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => start(quickPreset("custom-openai")!)}
                >
                  <KeyRound data-icon="inline-start" />
                  {t("assistant.providers.customQuick")}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}

        {providers.length > 0 ? (
          <div className="space-y-1.5">
            {providers.map((provider) => {
              const isActive = provider.id === selected?.id && !isCreating && !picking;
              const name = presetBadgeLabel(provider, presetsById, english);
              return (
                <button
                  key={provider.id}
                  type="button"
                  onClick={() => {
                    setCreating(null);
                    setPicking(false);
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
                      {name} · {provider.model}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {provider.isLocal ? (
                      <Badge variant="secondary" className="font-normal">
                        {t("assistant.providers.localBadge")}
                      </Badge>
                    ) : null}
                    {provider.needsKey && !provider.isLocal ? (
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

        {picking ? (
          <PresetPicker
            presets={presets}
            loading={presetsLoading}
            failed={presetsFailed}
            onPick={start}
            onCancel={() => setPicking(false)}
          />
        ) : null}

        {creating ? (
          <ProviderForm
            key={`preset:${creating.id}`}
            provider={null}
            preset={creating}
            presetsById={presetsById}
            autoFocusKey={creating.needsKey}
            onSaved={saved}
            onCancel={() => setCreating(null)}
            onError={onError}
          />
        ) : selected ? (
          <ProviderForm
            key={selected.id}
            provider={selected}
            preset={selectedPreset}
            presetsById={presetsById}
            onSaved={saved}
            onDeleted={deleted}
            onError={onError}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

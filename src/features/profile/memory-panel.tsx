import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { LoaderCircle, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api/error";
import { intlLocale } from "@/lib/i18n";
import { useMemory, useUpdateMemory } from "./use-profile-data";

const MAX_MEMORY_CHARS = 20_000;

interface Draft {
  content: string;
  enabled: boolean;
}

const EMPTY_DRAFT: Draft = { content: "", enabled: false };

export function MemoryPanel({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const query = useMemory();
  const mutation = useUpdateMemory();

  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [baseline, setBaseline] = useState<Draft>(EMPTY_DRAFT);
  const [saved, setSaved] = useState(false);

  const updatedAt = query.data?.updatedAt;

  useEffect(() => {
    if (!query.data) return;
    const next = { content: query.data.content, enabled: query.data.enabled };
    setDraft(next);
    setBaseline(next);
    setSaved(false);
  }, [updatedAt]);

  const dirty = draft.content !== baseline.content || draft.enabled !== baseline.enabled;
  const invalid = draft.content.length > MAX_MEMORY_CHARS;

  const onSave = () => {
    if (invalid) return;
    mutation.mutate(draft, {
      onSuccess: () => {
        setSaved(true);
        toast.success(t("profile.memory.saved"));
      },
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const formatUpdatedAt = (value: string) =>
    new Intl.DateTimeFormat(intlLocale(i18n.language), {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));

  if (query.isLoading) {
    return (
      <Card className={className}>
        <CardContent className="space-y-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (query.isError) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-between gap-4">
          <p className="eh-small text-muted-foreground">{t("profile.memory.loadError")}</p>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            <RefreshCw data-icon="inline-start" />
            {t("profile.memory.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("profile.memory.title")}</CardTitle>
        <CardDescription>{t("profile.memory.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="profile-memory-content">{t("profile.memory.content")}</Label>
          <Textarea
            id="profile-memory-content"
            rows={6}
            maxLength={MAX_MEMORY_CHARS}
            placeholder={t("profile.memory.placeholder")}
            value={draft.content}
            onChange={(event) => {
              setDraft((current) => ({ ...current, content: event.target.value }));
              setSaved(false);
            }}
          />
          <p className="eh-caption text-muted-foreground">
            {t("profile.memory.counter", {
              used: draft.content.length,
              max: MAX_MEMORY_CHARS,
            })}
          </p>
        </div>

        <div className="flex items-center justify-between gap-4 rounded-xl border border-border px-3 py-2.5">
          <div className="space-y-0.5">
            <Label htmlFor="profile-memory-enabled">{t("profile.memory.enabled")}</Label>
            <p className="eh-caption text-muted-foreground">
              {t("profile.memory.enabledHint")}
            </p>
          </div>
          <Switch
            id="profile-memory-enabled"
            checked={draft.enabled}
            onCheckedChange={(checked) => {
              setDraft((current) => ({ ...current, enabled: checked }));
              setSaved(false);
            }}
          />
        </div>

        {invalid ? (
          <p className="eh-small text-destructive" role="alert">
            {t("profile.memory.tooLong", { max: MAX_MEMORY_CHARS })}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onSave} disabled={!dirty || invalid || mutation.isPending}>
            {mutation.isPending ? (
              <LoaderCircle className="animate-spin" data-icon="inline-start" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            {mutation.isPending ? t("profile.memory.saving") : t("profile.memory.save")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => setDraft(baseline)}
            disabled={!dirty || mutation.isPending}
          >
            {t("profile.memory.cancel")}
          </Button>
          {saved && !dirty ? (
            <span className="eh-caption text-muted-foreground" role="status">
              {t("profile.memory.saved")}
            </span>
          ) : null}
          {updatedAt ? (
            <span className="eh-caption text-muted-foreground">
              {t("profile.memory.updatedAt", { date: formatUpdatedAt(updatedAt) })}
            </span>
          ) : null}
        </div>

        <p className="flex items-start gap-1.5 eh-caption text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {t("profile.memory.privacy")}
        </p>
      </CardContent>
    </Card>
  );
}

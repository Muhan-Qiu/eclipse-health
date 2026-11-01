import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Copy,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { baseUrl } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/error";
import { formatDateTime } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import {
  createExternalKey,
  EXTERNAL_RECORDS_URL,
  isExternalUnavailable,
  listExternalKeys,
  MCP_COMMAND,
  OPENAI_API_BASE,
  OPENAI_MODEL,
  revokeExternalKey,
} from "./api";
import {
  EXTERNAL_SCOPES,
  type CreatedExternalKey,
  type ExternalKey,
  type ExternalKeysState,
  type ExternalScope,
} from "./types";

interface ExternalAccessPanelProps {
  className?: string;
}

const DEFAULT_SCOPES: ExternalScope[] = ["read", "write"];
const NAME_MAX_LENGTH = 64;

const MCP_EXAMPLE = [
  `EH_API_BASE=${baseUrl} \\`,
  "EH_EXTERNAL_KEY=**** \\",
  MCP_COMMAND,
].join("\n");

const REST_EXAMPLE = [
  'curl -H "Authorization: Bearer ****" \\',
  `  ${EXTERNAL_RECORDS_URL}`,
].join("\n");

const OPENAI_EXAMPLE = [
  "from openai import OpenAI",
  "",
  "client = OpenAI(",
  `    base_url="${OPENAI_API_BASE}",`,
  '    api_key="****",',
  ")",
  "print(client.chat.completions.create(",
  `    model="${OPENAI_MODEL}",`,
  '    messages=[{"role": "user", "content": "总结最近的记录"}],',
  ").choices[0].message.content)",
].join("\n");

function formatTime(iso: string, locale: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return formatDateTime(iso, locale);
}

export function ExternalAccessPanel({ className }: ExternalAccessPanelProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);

  const [keysState, setKeysState] = useState<ExternalKeysState | "loading">(
    "loading",
  );
  const [reloadToken, setReloadToken] = useState(0);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<ExternalScope[]>(DEFAULT_SCOPES);
  const [created, setCreated] = useState<CreatedExternalKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setKeysState("loading");
    listExternalKeys()
      .then((state) => {
        if (active) setKeysState(state);
      })
      .catch(() => {
        if (active) setKeysState({ status: "unavailable" });
      });
    return () => {
      active = false;
    };
  }, [reloadToken]);

  function reload() {
    setReloadToken((value) => value + 1);
  }

  function openCreate() {
    setName("");
    setScopes(DEFAULT_SCOPES);
    setCreated(null);
    setFormError(null);
    setDialogOpen(true);
  }

  function closeDialog() {
    if (creating) return;
    const shouldReload = created !== null;
    setDialogOpen(false);
    setCreated(null);
    setName("");
    setScopes(DEFAULT_SCOPES);
    setFormError(null);
    if (shouldReload) reload();
  }

  function toggleScope(scope: ExternalScope, checked: boolean) {
    setScopes((current) =>
      checked
        ? EXTERNAL_SCOPES.filter(
            (item) => item === scope || current.includes(item),
          )
        : current.filter((item) => item !== scope),
    );
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("settings.external.copied"));
    } catch {
      toast.error(t("settings.external.copyFailed"));
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setFormError(t("settings.external.nameRequired"));
      return;
    }
    if (trimmed.length > NAME_MAX_LENGTH) {
      setFormError(t("settings.external.nameTooLong"));
      return;
    }
    if (scopes.length === 0) {
      setFormError(t("settings.external.scopeRequired"));
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const key = await createExternalKey({ name: trimmed, scopes });
      setCreated(key);
    } catch (error) {
      setFormError(
        isExternalUnavailable(error)
          ? t("settings.external.unavailableTitle")
          : errorMessage(error),
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    setRevokingId(id);
    try {
      await revokeExternalKey(id);
      toast.success(t("settings.external.revokeDone"));
      setConfirmRevokeId(null);
      reload();
    } catch (error) {
      if (isExternalUnavailable(error)) {
        setKeysState({ status: "unavailable" });
      }
      toast.error(t("settings.external.revokeFailed"), {
        description: errorMessage(error),
      });
    } finally {
      setRevokingId(null);
    }
  }

  const items = keysState === "loading" ? [] : keysState.status === "ok" ? keysState.items : [];

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="eh-h3">
              {t("settings.external.title")}
            </CardTitle>
            <CardDescription>
              {t("settings.external.description")}
            </CardDescription>
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={t("settings.external.refresh")}
              onClick={reload}
            >
              <RefreshCw aria-hidden="true" />
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={
                keysState !== "loading" && keysState.status === "unavailable"
              }
              onClick={openCreate}
            >
              <Plus aria-hidden="true" />
              {t("settings.external.create")}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {keysState === "loading" ? (
          <p className="eh-caption text-muted-foreground">
            {t("settings.external.loading")}
          </p>
        ) : keysState.status === "unavailable" ? (
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <p className="text-sm font-medium">
              {t("settings.external.unavailableTitle")}
            </p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("settings.external.unavailableDesc")}
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3"
              onClick={reload}
            >
              <RefreshCw aria-hidden="true" />
              {t("common.retry")}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-4">
            <p className="text-sm font-medium">
              {t("settings.external.emptyTitle")}
            </p>
            <p className="eh-caption mt-1 text-muted-foreground">
              {t("settings.external.emptyDesc")}
            </p>
          </div>
        ) : (
          <section className="space-y-2">
            <h3 className="eh-caption text-muted-foreground">
              {t("settings.external.listTitle")}
            </h3>
            <ul className="space-y-2">
              {items.map((entry) => (
                <KeyRow
                  key={entry.id}
                  entry={entry}
                  locale={locale}
                  confirmRevokeId={confirmRevokeId}
                  revokingId={revokingId}
                  onConfirm={() => setConfirmRevokeId(entry.id)}
                  onCancel={() => setConfirmRevokeId(null)}
                  onRevoke={() => void handleRevoke(entry.id)}
                />
              ))}
            </ul>
          </section>
        )}

        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <h3 className="eh-caption text-muted-foreground">
              {t("settings.external.examplesTitle")}
            </h3>
          </div>
          <p className="eh-caption text-muted-foreground">
            {t("settings.external.examplesDesc")}
          </p>
          <div className="grid gap-3">
            <ExampleCard
              title={t("settings.external.mcpTitle")}
              description={t("settings.external.mcpDesc")}
              code={MCP_EXAMPLE}
              copyLabel={t("settings.external.copyExample", {
                name: t("settings.external.mcpTitle"),
              })}
              onCopy={() => void copyText(MCP_EXAMPLE)}
            />
            <ExampleCard
              title={t("settings.external.restTitle")}
              description={t("settings.external.restDesc")}
              code={REST_EXAMPLE}
              copyLabel={t("settings.external.copyExample", {
                name: t("settings.external.restTitle"),
              })}
              onCopy={() => void copyText(REST_EXAMPLE)}
            />
            <ExampleCard
              title={t("settings.external.openaiTitle")}
              description={t("settings.external.openaiDesc")}
              code={OPENAI_EXAMPLE}
              copyLabel={t("settings.external.copyExample", {
                name: t("settings.external.openaiTitle"),
              })}
              onCopy={() => void copyText(OPENAI_EXAMPLE)}
            />
          </div>
        </section>
      </CardContent>

      <Dialog
        open={dialogOpen}
        onOpenChange={(next) => {
          if (!next) closeDialog();
        }}
      >
        <DialogContent className="sm:max-w-md" showCloseButton={!creating}>
          {created ? (
            <>
              <DialogHeader>
                <DialogTitle>{t("settings.external.tokenTitle")}</DialogTitle>
                <DialogDescription>
                  {t("settings.external.tokenDesc")}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <code className="block break-all rounded-lg border border-border bg-muted px-3 py-2 font-mono text-sm select-all">
                  {created.token}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void copyText(created.token)}
                >
                  <Copy aria-hidden="true" />
                  {t("settings.external.copy")}
                </Button>
                <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  {t("settings.external.tokenWarning")}
                </p>
              </div>
              <DialogFooter>
                <Button type="button" onClick={closeDialog}>
                  {t("settings.external.tokenDone")}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <form onSubmit={(event) => void handleCreate(event)}>
              <DialogHeader>
                <DialogTitle>{t("settings.external.createTitle")}</DialogTitle>
                <DialogDescription>
                  {t("settings.external.createDesc")}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-1.5">
                  <Label htmlFor="external-key-name">
                    {t("settings.external.nameLabel")}
                  </Label>
                  <Input
                    id="external-key-name"
                    value={name}
                    maxLength={NAME_MAX_LENGTH}
                    placeholder={t("settings.external.namePlaceholder")}
                    autoComplete="off"
                    disabled={creating}
                    onChange={(event) => setName(event.target.value)}
                  />
                </div>
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium">
                    {t("settings.external.scopesLabel")}
                  </legend>
                  {EXTERNAL_SCOPES.map((scope) => {
                    const id = `external-scope-${scope}`;
                    return (
                      <label
                        key={scope}
                        htmlFor={id}
                        className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border p-2.5 transition-colors has-checked:border-primary has-checked:bg-accent-soft"
                      >
                        <input
                          id={id}
                          type="checkbox"
                          className="mt-0.5 size-4 shrink-0 accent-primary"
                          checked={scopes.includes(scope)}
                          disabled={creating}
                          onChange={(event) =>
                            toggleScope(scope, event.target.checked)
                          }
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">
                            {t(`settings.external.scope.${scope}`)}
                          </span>
                          <span className="eh-caption block text-muted-foreground">
                            {t(`settings.external.scopeDesc.${scope}`)}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </fieldset>
                {formError ? (
                  <p role="alert" className="text-sm text-destructive">
                    {formError}
                  </p>
                ) : null}
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  disabled={creating}
                  onClick={closeDialog}
                >
                  {t("common.cancel")}
                </Button>
                <Button type="submit" disabled={creating}>
                  {creating ? (
                    <Loader2 className="animate-spin" aria-hidden="true" />
                  ) : (
                    <KeyRound aria-hidden="true" />
                  )}
                  {creating
                    ? t("settings.external.creating")
                    : t("settings.external.createAction")}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

interface KeyRowProps {
  entry: ExternalKey;
  locale: string;
  confirmRevokeId: string | null;
  revokingId: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  onRevoke: () => void;
}

function KeyRow({
  entry,
  locale,
  confirmRevokeId,
  revokingId,
  onConfirm,
  onCancel,
  onRevoke,
}: KeyRowProps) {
  const { t } = useTranslation();
  const revoked = entry.revokedAt !== null;
  const createdAt = formatTime(entry.createdAt, locale);
  const lastUsedAt = entry.lastUsedAt
    ? formatTime(entry.lastUsedAt, locale)
    : null;
  const confirming = confirmRevokeId === entry.id;
  const revoking = revokingId === entry.id;

  return (
    <li
      className={cn(
        "rounded-lg border border-border p-3",
        revoked && "opacity-60",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p
            className={cn(
              "truncate text-sm font-medium",
              revoked && "line-through",
            )}
          >
            {entry.name}
          </p>
          <code className="eh-caption text-muted-foreground">
            {entry.prefix ? `${entry.prefix}…` : "…"}
          </code>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {entry.scopes.map((scope) => (
            <Badge key={scope} variant="outline">
              {t(`settings.external.scopeLabel.${scope}`)}
            </Badge>
          ))}
          {revoked ? (
            <Badge variant="secondary">{t("settings.external.revoked")}</Badge>
          ) : null}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="eh-caption text-muted-foreground">
          {createdAt
            ? t("settings.external.createdAt", { time: createdAt })
            : null}
          {createdAt ? " · " : null}
          {lastUsedAt
            ? t("settings.external.lastUsed", { time: lastUsedAt })
            : t("settings.external.neverUsed")}
        </span>
        {revoked ? null : confirming ? (
          <span className="flex items-center gap-1.5">
            <Button
              type="button"
              size="xs"
              variant="destructive"
              disabled={revoking}
              onClick={onRevoke}
            >
              {revoking ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : null}
              {t("settings.external.revokeConfirm")}
            </Button>
            <Button
              type="button"
              size="xs"
              variant="ghost"
              disabled={revoking}
              onClick={onCancel}
            >
              {t("common.cancel")}
            </Button>
          </span>
        ) : (
          <Button type="button" size="xs" variant="ghost" onClick={onConfirm}>
            {t("settings.external.revoke")}
          </Button>
        )}
      </div>
    </li>
  );
}

interface ExampleCardProps {
  title: string;
  description: string;
  code: string;
  copyLabel: string;
  onCopy: () => void;
}

function ExampleCard({
  title,
  description,
  code,
  copyLabel,
  onCopy,
}: ExampleCardProps) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{title}</p>
          <p className="eh-caption text-muted-foreground">{description}</p>
        </div>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label={copyLabel}
          onClick={onCopy}
        >
          <Copy aria-hidden="true" />
        </Button>
      </div>
      <pre className="mt-2 overflow-x-auto rounded-md bg-muted px-2.5 py-2 font-mono text-[0.7rem] leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Save } from "lucide-react";
import { toast } from "sonner";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api/error";
import type { Member } from "@/lib/api/types";
import { ExercisePanel } from "./exercise-panel";
import { MemoryPanel } from "./memory-panel";
import { useMembers, useUpdateMember } from "./use-profile-data";
import type { MemberPatch, MemberSex, ProfileMember } from "./types";

const MAX_ITEMS = 32;
const MAX_ITEM_LENGTH = 64;
const MAX_NOTES = 4000;
const SLEEP_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

interface Draft {
  birthYear: string;
  sex: MemberSex;
  heightCm: string;
  weightKg: string;
  restingHeartRate: string;
  sleepStart: string;
  sleepEnd: string;
  conditions: string;
  medications: string;
  notes: string;
}

const EMPTY_DRAFT: Draft = {
  birthYear: "",
  sex: "unknown",
  heightCm: "",
  weightKg: "",
  restingHeartRate: "",
  sleepStart: "",
  sleepEnd: "",
  conditions: "",
  medications: "",
  notes: "",
};

function draftFrom(member: Member): Draft {
  const extended = member as Member & ProfileMember;
  return {
    birthYear: member.birthYear ? String(member.birthYear) : "",
    sex: member.sex ?? "unknown",
    heightCm: member.heightCm !== undefined && member.heightCm !== null
      ? String(member.heightCm)
      : "",
    weightKg: member.weightKg !== undefined && member.weightKg !== null
      ? String(member.weightKg)
      : "",
    restingHeartRate:
      extended.restingHeartRate !== undefined && extended.restingHeartRate !== null
        ? String(extended.restingHeartRate)
        : "",
    sleepStart: extended.sleepStart ?? "",
    sleepEnd: extended.sleepEnd ?? "",
    conditions: (member.conditions ?? []).join("\n"),
    medications: (member.medications ?? []).join("\n"),
    notes: member.notes ?? "",
  };
}

function resolvedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return Number(trimmed);
}

type InvalidKey =
  | "birthYear"
  | "heightCm"
  | "weightKg"
  | "restingHeartRate"
  | "sleepStart"
  | "sleepEnd"
  | "conditions"
  | "medications"
  | "notes";

function validate(draft: Draft): InvalidKey | null {
  if (draft.birthYear.trim()) {
    const year = Number(draft.birthYear);
    if (!Number.isInteger(year) || year < 1900 || year > 2100) return "birthYear";
  }
  if (draft.heightCm.trim()) {
    const height = Number(draft.heightCm);
    if (!Number.isFinite(height) || height < 30 || height > 300) return "heightCm";
  }
  if (draft.weightKg.trim()) {
    const weight = Number(draft.weightKg);
    if (!Number.isFinite(weight) || weight < 2 || weight > 500) return "weightKg";
  }
  if (draft.restingHeartRate.trim()) {
    const rate = Number(draft.restingHeartRate);
    if (!Number.isInteger(rate) || rate < 30 || rate > 200) return "restingHeartRate";
  }
  if (draft.sleepStart.trim() && !SLEEP_PATTERN.test(draft.sleepStart.trim())) {
    return "sleepStart";
  }
  if (draft.sleepEnd.trim() && !SLEEP_PATTERN.test(draft.sleepEnd.trim())) {
    return "sleepEnd";
  }
  for (const [key, value] of [
    ["conditions", draft.conditions],
    ["medications", draft.medications],
  ] as const) {
    const items = splitLines(value);
    if (items.length > MAX_ITEMS) return key;
    if (items.some((item) => item.length > MAX_ITEM_LENGTH)) return key;
  }
  if (draft.notes.length > MAX_NOTES) return "notes";
  return null;
}

function patchFrom(draft: Draft): MemberPatch {
  const conditions = splitLines(draft.conditions);
  const medications = splitLines(draft.medications);
  const hasSleep = Boolean(draft.sleepStart.trim() || draft.sleepEnd.trim());
  return {
    birthYear: optionalNumber(draft.birthYear),
    sex: draft.sex,
    heightCm: optionalNumber(draft.heightCm),
    weightKg: optionalNumber(draft.weightKg),
    restingHeartRate: optionalNumber(draft.restingHeartRate),
    sleepStart: draft.sleepStart.trim() || null,
    sleepEnd: draft.sleepEnd.trim() || null,
    sleepTimezone: hasSleep ? resolvedTimezone() : null,
    conditions,
    medications,
    notes: draft.notes,
  };
}

export function ProfileForm({ className }: { className?: string }) {
  const { t } = useTranslation();
  const membersQuery = useMembers();
  const member = membersQuery.data?.[0];
  const mutation = useUpdateMember();

  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [baseline, setBaseline] = useState<Draft>(EMPTY_DRAFT);
  const [saved, setSaved] = useState(false);

  const memberUpdatedAt = member?.updatedAt;

  useEffect(() => {
    if (!member) return;
    const next = draftFrom(member);
    setDraft(next);
    setBaseline(next);
    // 只在服务端版本变化时重置草稿，避免窗口重新聚焦时的后台刷新覆盖正在编辑的内容。
  }, [memberUpdatedAt]);

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setSaved(false);
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const invalid = validate(draft);

  const onSave = () => {
    if (!member || invalid) return;
    mutation.mutate(
      { id: member.id, patch: patchFrom(draft), current: member },
      {
        onSuccess: () => {
          setSaved(true);
          toast.success(t("profile.basics.saved"));
        },
        onError: (error) => {
          toast.error(errorMessage(error));
        },
      },
    );
  };

  if (membersQuery.isLoading) {
    return (
      <Card className={className}>
        <CardContent className="space-y-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (membersQuery.isError || !member) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-between gap-4">
          <p className="eh-small text-muted-foreground">
            {t("profile.basics.loadError")}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void membersQuery.refetch()}
          >
            <RefreshCw data-icon="inline-start" />
            {t("profile.basics.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      <Card>
        <CardHeader>
        <CardTitle className="eh-h3">{t("profile.basics.title")}</CardTitle>
        <CardDescription>{t("profile.basics.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="profile-birth-year">
              {t("profile.basics.birthYear")}
            </Label>
            <Input
              id="profile-birth-year"
              inputMode="numeric"
              className="eh-num"
              placeholder={t("profile.basics.birthYearPlaceholder")}
              value={draft.birthYear}
              onChange={(event) => update("birthYear", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-sex">{t("profile.basics.sex")}</Label>
            <Select
              value={draft.sex}
              onValueChange={(value) => update("sex", value as MemberSex)}
            >
              <SelectTrigger id="profile-sex" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["female", "male", "other", "unknown"] as const).map((sex) => (
                  <SelectItem key={sex} value={sex}>
                    {t(`profile.basics.sexOptions.${sex}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-height">{t("profile.basics.heightCm")}</Label>
            <Input
              id="profile-height"
              inputMode="decimal"
              className="eh-num"
              value={draft.heightCm}
              onChange={(event) => update("heightCm", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-weight">{t("profile.basics.weightKg")}</Label>
            <Input
              id="profile-weight"
              inputMode="decimal"
              className="eh-num"
              value={draft.weightKg}
              onChange={(event) => update("weightKg", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-resting-heart-rate">
              {t("profile.basics.restingHeartRate")}
            </Label>
            <Input
              id="profile-resting-heart-rate"
              inputMode="numeric"
              className="eh-num"
              placeholder={t("profile.basics.restingHeartRatePlaceholder")}
              value={draft.restingHeartRate}
              onChange={(event) => update("restingHeartRate", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-sleep-start">
              {t("profile.basics.sleepStart")}
            </Label>
            <Input
              id="profile-sleep-start"
              type="time"
              className="eh-num"
              value={draft.sleepStart}
              onChange={(event) => update("sleepStart", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-sleep-end">{t("profile.basics.sleepEnd")}</Label>
            <Input
              id="profile-sleep-end"
              type="time"
              className="eh-num"
              value={draft.sleepEnd}
              onChange={(event) => update("sleepEnd", event.target.value)}
            />
            <p className="eh-caption text-muted-foreground">
              {t("profile.basics.sleepHint")}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-conditions">
              {t("profile.basics.conditions")}
            </Label>
            <Textarea
              id="profile-conditions"
              rows={3}
              value={draft.conditions}
              onChange={(event) => update("conditions", event.target.value)}
            />
            <p className="eh-caption text-muted-foreground">
              {t("profile.basics.conditionsHint")}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-medications">
              {t("profile.basics.medications")}
            </Label>
            <Textarea
              id="profile-medications"
              rows={3}
              value={draft.medications}
              onChange={(event) => update("medications", event.target.value)}
            />
            <p className="eh-caption text-muted-foreground">
              {t("profile.basics.medicationsHint")}
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="profile-notes">{t("profile.basics.notes")}</Label>
          <Textarea
            id="profile-notes"
            rows={3}
            maxLength={MAX_NOTES}
            placeholder={t("profile.basics.notesPlaceholder")}
            value={draft.notes}
            onChange={(event) => update("notes", event.target.value)}
          />
        </div>

        {invalid ? (
          <p className="eh-small text-destructive" role="alert">
            {t(`profile.basics.invalid.${invalid}`)}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onSave} disabled={!dirty || Boolean(invalid) || mutation.isPending}>
            <Save data-icon="inline-start" />
            {mutation.isPending
              ? t("profile.basics.saving")
              : t("profile.basics.save")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => setDraft(baseline)}
            disabled={!dirty || mutation.isPending}
          >
            {t("profile.basics.cancel")}
          </Button>
          {saved && !dirty ? (
            <span className="eh-caption text-muted-foreground" role="status">
              {t("profile.basics.saved")}
            </span>
          ) : null}
        </div>
      </CardContent>
      </Card>
      <ExercisePanel />
      <MemoryPanel />
    </div>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Activity, LoaderCircle, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
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
import { EmptyState } from "@/components/common/empty-state";
import { errorMessage } from "@/lib/api/error";
import { intlLocale } from "@/lib/i18n";
import { useCreateExercise, useDeleteExercise, useExercises } from "./use-profile-data";
import { EXERCISE_ACTIVITIES } from "./types";
import type { Exercise, ExerciseActivity, ExerciseIntensity, ExerciseSubjective } from "./types";

const NONE = "none";
const MAX_MINUTES = 24 * 60;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function localInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function resolvedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const number = Number(trimmed);
  return Number.isFinite(number) ? number : null;
}

function ExerciseRow({ exercise, onDelete }: { exercise: Exercise; onDelete: () => void }) {
  const { t, i18n } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const deleteMutation = useDeleteExercise();

  const date = new Intl.DateTimeFormat(intlLocale(i18n.language), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(exercise.startAt));

  const minutes = Math.round(exercise.durationSec / 60);
  const details = [
    t("profile.exercise.minutesShort", { minutes }),
    exercise.distanceKm != null ? `${exercise.distanceKm} km` : null,
    exercise.intensity
      ? t(`profile.exercise.intensityOptions.${exercise.intensity}`)
      : null,
    exercise.subjective,
  ].filter(Boolean);

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
      <span className="eh-caption w-36 shrink-0 text-muted-foreground">{date}</span>
      <span className="eh-small min-w-16 font-medium">
        {t(`profile.exercise.activities.${exercise.activity}`)}
      </span>
      <span className="eh-num text-sm text-muted-foreground">{details.join(" · ")}</span>
      {exercise.notes ? (
        <span className="eh-caption min-w-0 flex-1 truncate text-muted-foreground">
          {exercise.notes}
        </span>
      ) : (
        <span className="flex-1" />
      )}
      {confirming ? (
        <span className="flex items-center gap-1">
          <Button
            variant="destructive"
            size="sm"
            disabled={deleteMutation.isPending}
            onClick={() =>
              deleteMutation.mutate(exercise.id, {
                onSuccess: onDelete,
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            {t("profile.exercise.deleteConfirm")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
            {t("common.cancel")}
          </Button>
        </span>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          aria-label={t("profile.exercise.delete")}
          onClick={() => setConfirming(true)}
        >
          <Trash2 aria-hidden="true" />
        </Button>
      )}
    </li>
  );
}

export function ExercisePanel({ className }: { className?: string }) {
  const { t } = useTranslation();
  const query = useExercises({ limit: 20 });
  const createMutation = useCreateExercise();

  const [activity, setActivity] = useState<ExerciseActivity>("walk");
  const [minutes, setMinutes] = useState("");
  const [distance, setDistance] = useState("");
  const [intensity, setIntensity] = useState<ExerciseIntensity | typeof NONE>(NONE);
  const [subjective, setSubjective] = useState<ExerciseSubjective | typeof NONE>(NONE);
  const [notes, setNotes] = useState("");
  const [startAt, setStartAt] = useState(() => localInputValue(new Date()));

  const duration = Number(minutes);
  const durationValid =
    minutes.trim() !== "" && Number.isFinite(duration) && duration > 0 && duration <= MAX_MINUTES;
  const distanceValue = parseOptionalNumber(distance);
  const distanceValid = distanceValue === null || distanceValue >= 0;

  const submit = () => {
    if (!durationValid || !distanceValid || !startAt) {
      toast.error(t("profile.exercise.invalid"));
      return;
    }
    createMutation.mutate(
      {
        activity,
        durationSec: Math.round(duration * 60),
        distanceKm: distanceValue,
        intensity: intensity === NONE ? null : intensity,
        subjective: subjective === NONE ? null : subjective,
        notes: notes.trim(),
        startAt: new Date(startAt).toISOString(),
        timezone: resolvedTimezone(),
      },
      {
        onSuccess: () => {
          setMinutes("");
          setDistance("");
          setNotes("");
          toast.success(t("profile.exercise.added"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const items = query.data?.items ?? [];

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("profile.exercise.title")}</CardTitle>
        <CardDescription>{t("profile.exercise.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-3">
          <h3 className="eh-caption text-muted-foreground">
            {t("profile.exercise.quickEntry")}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="exercise-activity">{t("profile.exercise.activity")}</Label>
              <Select
                value={activity}
                onValueChange={(value) => setActivity(value as ExerciseActivity)}
              >
                <SelectTrigger id="exercise-activity" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXERCISE_ACTIVITIES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`profile.exercise.activities.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exercise-minutes">{t("profile.exercise.minutes")}</Label>
              <Input
                id="exercise-minutes"
                inputMode="numeric"
                className="eh-num"
                placeholder={t("profile.exercise.minutesPlaceholder")}
                value={minutes}
                onChange={(event) => setMinutes(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exercise-distance">{t("profile.exercise.distance")}</Label>
              <Input
                id="exercise-distance"
                inputMode="decimal"
                className="eh-num"
                placeholder={t("profile.exercise.optional")}
                value={distance}
                onChange={(event) => setDistance(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exercise-intensity">{t("profile.exercise.intensity")}</Label>
              <Select
                value={intensity}
                onValueChange={(value) =>
                  setIntensity(value as ExerciseIntensity | typeof NONE)
                }
              >
                <SelectTrigger id="exercise-intensity" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>{t("profile.exercise.notFilled")}</SelectItem>
                  {(["low", "moderate", "vigorous"] as const).map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`profile.exercise.intensityOptions.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exercise-subjective">{t("profile.exercise.subjective")}</Label>
              <Select
                value={subjective}
                onValueChange={(value) =>
                  setSubjective(value as ExerciseSubjective | typeof NONE)
                }
              >
                <SelectTrigger id="exercise-subjective" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>{t("profile.exercise.notFilled")}</SelectItem>
                  {(["轻松", "适中", "吃力"] as const).map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exercise-start-at">{t("profile.exercise.startAt")}</Label>
              <Input
                id="exercise-start-at"
                type="datetime-local"
                className="eh-num"
                value={startAt}
                onChange={(event) => setStartAt(event.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="exercise-notes">{t("profile.exercise.notes")}</Label>
            <Textarea
              id="exercise-notes"
              rows={1}
              className="min-h-9"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
          <Button
            size="sm"
            onClick={submit}
            disabled={createMutation.isPending || !durationValid || !distanceValid}
          >
            {createMutation.isPending ? (
              <LoaderCircle className="animate-spin" data-icon="inline-start" />
            ) : (
              <Plus data-icon="inline-start" />
            )}
            {createMutation.isPending
              ? t("profile.exercise.adding")
              : t("profile.exercise.add")}
          </Button>
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="eh-h3">{t("profile.exercise.recentTitle")}</h3>
            <span className="eh-caption text-muted-foreground">
              {t("profile.exercise.total", { total: query.data?.total ?? 0 })}
            </span>
          </div>

          {query.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : null}

          {query.isError ? (
            <EmptyState
              icon={RefreshCw}
              title={t("profile.exercise.loadError")}
              description={t("profile.exercise.description")}
            >
              <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                <RefreshCw data-icon="inline-start" />
                {t("profile.exercise.retry")}
              </Button>
            </EmptyState>
          ) : null}

          {!query.isLoading && !query.isError && items.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={t("profile.exercise.emptyTitle")}
              description={t("profile.exercise.emptyDesc")}
            />
          ) : null}

          {items.length > 0 ? (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {items.map((exercise) => (
                <ExerciseRow key={exercise.id} exercise={exercise} onDelete={() => undefined} />
              ))}
            </ul>
          ) : null}
        </section>
      </CardContent>
    </Card>
  );
}

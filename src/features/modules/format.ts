import type { TFunction } from "i18next";

export function formatDateTime(
  value: string | null | undefined,
  locale: string,
): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function moduleTypeLabel(t: TFunction, type: string): string {
  return t(`moduleUi.types.${type}`, { defaultValue: type });
}

export function moduleStateLabel(t: TFunction, state: string): string {
  return t(`moduleUi.states.${state}`, { defaultValue: state });
}

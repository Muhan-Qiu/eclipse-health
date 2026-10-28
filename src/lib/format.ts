export function formatDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "long" }).format(
    new Date(iso),
  );
}

export function formatDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function formatFullDate(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

export function formatPercent(ratio: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(ratio);
}

export function formatNumber(
  value: number,
  locale: string,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(locale, options).format(value);
}

/** 时长显示为 m:ss（等宽数字，不随语言变化分隔符）。 */
export function formatDuration(seconds: number, locale: string): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  const minuteText = new Intl.NumberFormat(locale).format(minutes);
  const restText = new Intl.NumberFormat(locale, {
    minimumIntegerDigits: 2,
    useGrouping: false,
  }).format(rest);
  return `${minuteText}:${restText}`;
}

export type GreetingKey =
  | "greeting.morning"
  | "greeting.afternoon"
  | "greeting.evening"
  | "greeting.night";

export function greetingKey(date = new Date()): GreetingKey {
  const hour = date.getHours();
  if (hour < 5) return "greeting.night";
  if (hour < 12) return "greeting.morning";
  if (hour < 18) return "greeting.afternoon";
  return "greeting.evening";
}

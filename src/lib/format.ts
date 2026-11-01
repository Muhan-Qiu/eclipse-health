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

/**
 * 时长统一为整秒：< 1 分钟 `0:SS`，< 1 小时 `M:SS`，否则 `H:MM:SS`。
 * 不显示毫秒，同一列表内的精度因此恒定；波形/分析内部的秒级小数走 `formatClock`。
 */
export function formatDuration(seconds: number, locale: string): string {
  const total =
    Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds) : 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const number = new Intl.NumberFormat(locale, {
    minimumIntegerDigits: 2,
    useGrouping: false,
  });
  if (hours > 0) {
    const hourText = new Intl.NumberFormat(locale).format(hours);
    return `${hourText}:${number.format(minutes)}:${number.format(rest)}`;
  }
  return `${new Intl.NumberFormat(locale).format(minutes)}:${number.format(rest)}`;
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

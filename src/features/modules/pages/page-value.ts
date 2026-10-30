import type { TFunction } from "i18next";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import type { PageValueFormat } from "./page-api";

/**
 * 受限路径读取：只支持 `a.b[0].c` 这类点/索引路径，不执行表达式。
 * 路径来自 manifest，已被 JSON Schema 约束；这里仍然拒绝原型链键。
 */

const PATH_PATTERN =
  /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+|\[[0-9]+\])*$/;
const BLOCKED_SEGMENTS = new Set(["__proto__", "constructor", "prototype"]);
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;

function parsePath(path: string): (string | number)[] | null {
  if (!PATH_PATTERN.test(path)) return null;
  const tokens: (string | number)[] = [];
  let index = 0;
  while (index < path.length) {
    const char = path[index];
    if (char === ".") {
      index += 1;
      continue;
    }
    if (char === "[") {
      const end = path.indexOf("]", index);
      if (end === -1) return null;
      tokens.push(Number(path.slice(index + 1, end)));
      index = end + 1;
      continue;
    }
    const match = /^[A-Za-z0-9_]+/.exec(path.slice(index));
    if (!match) return null;
    tokens.push(match[0]);
    index += match[0].length;
  }
  return tokens;
}

export function readPath(source: unknown, path?: string): unknown {
  if (!path) return source;
  const tokens = parsePath(path);
  if (!tokens) return undefined;

  let current: unknown = source;
  for (const token of tokens) {
    if (typeof token === "number") {
      if (!Array.isArray(current)) return undefined;
      current = current[token];
      continue;
    }
    if (BLOCKED_SEGMENTS.has(token)) return undefined;
    if (
      typeof current !== "object" ||
      current === null ||
      !Object.prototype.hasOwnProperty.call(current, token)
    ) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[token];
  }
  return current;
}

function safeDate(value: string): Date | null {
  const date = new Date(
    DATE_ONLY.test(value) ? `${value}T00:00:00` : value,
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

function tryFormat(
  value: string,
  kind: "date" | "datetime",
  locale: string,
): string | null {
  const date = safeDate(value);
  if (!date) return null;
  try {
    const iso = date.toISOString();
    return kind === "date"
      ? formatDate(iso, locale)
      : formatDateTime(iso, locale);
  } catch {
    return null;
  }
}

function jsonPreview(value: unknown): string {
  try {
    const text = JSON.stringify(value);
    if (text === undefined) return String(value);
    return text.length > 200 ? `${text.slice(0, 200)}…` : text;
  } catch {
    return String(value);
  }
}

export interface ValueFormatOptions {
  format?: PageValueFormat;
  unit?: string;
}

export function formatPageValue(
  value: unknown,
  options: ValueFormatOptions,
  locale: string,
  t: TFunction,
): string {
  if (value === null || value === undefined || value === "") {
    return t("modulePage.emptyValue");
  }
  if (typeof value === "boolean") {
    return value ? t("modulePage.yes") : t("modulePage.no");
  }

  let text: string;
  if (typeof value === "number") {
    text = formatNumber(value, locale, { maximumFractionDigits: 2 });
  } else if (typeof value === "string") {
    const formatted =
      options.format === "date"
        ? tryFormat(value, "date", locale)
        : options.format === "datetime"
          ? tryFormat(value, "datetime", locale)
          : options.format === "text" || options.format === "number"
            ? null
            : DATE_TIME.test(value)
              ? tryFormat(value, "datetime", locale)
              : DATE_ONLY.test(value)
                ? tryFormat(value, "date", locale)
                : null;
    text = formatted ?? value;
  } else {
    text = jsonPreview(value);
  }

  return options.unit ? `${text} ${options.unit}` : text;
}

/** 把 RPC 结果按字段 key 回填到表单初值。 */
export function valuesFromRecord(
  data: unknown,
  fields: { key: string }[],
): Record<string, string | boolean> {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return {};
  }
  const values: Record<string, string | boolean> = {};
  for (const field of fields) {
    const raw = readPath(data, field.key);
    if (typeof raw === "string") values[field.key] = raw;
    else if (typeof raw === "number") values[field.key] = String(raw);
    else if (typeof raw === "boolean") values[field.key] = raw;
  }
  return values;
}

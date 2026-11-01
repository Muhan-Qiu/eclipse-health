/**
 * 仪表盘布局：纯数据层，不依赖 React / i18n。
 *
 * 存储形状 `{ version: 1, items: LayoutItem[] }`；旧版裸数组也能读入并迁移。
 * 读取失败、版本不认识、条目非法都退回默认布局，绝不让坏数据卡住首页。
 */

export const LAYOUT_STORAGE_KEY = "eh-dashboard-layout-v1";
export const LAYOUT_VERSION = 1;
export const LAYOUT_MAX_ITEMS = 64;
export const LAYOUT_ID_MAX = 200;
export const LAYOUT_TITLE_MAX = 120;

export const LAYOUT_WIDTHS = [3, 6, 9, 12] as const;
export type LayoutWidth = (typeof LAYOUT_WIDTHS)[number];
export type LayoutItemKind = "module-widget" | "core-card";

export interface LayoutItem {
  id: string;
  kind: LayoutItemKind;
  title: string;
  width: LayoutWidth;
  hidden: boolean;
}

export type CoreCardId =
  | "scores"
  | "suggestions"
  | "health-summary"
  | "recent"
  | "metrics"
  | "waveform";

interface CoreCardDefault {
  id: CoreCardId;
  width: LayoutWidth;
  /** 仅作导出/迁移时的兜底标题；显示时由页面按 i18n 覆盖。 */
  title: string;
}

/** 默认顺序与旧仪表盘一致；模块卡片由 mergeLayout 插在「最近记录」之前。 */
const CORE_CARDS: readonly CoreCardDefault[] = [
  { id: "scores", width: 9, title: "Health score" },
  { id: "suggestions", width: 3, title: "Suggestions" },
  { id: "health-summary", width: 12, title: "Health data" },
  { id: "recent", width: 6, title: "Recent records" },
  { id: "metrics", width: 6, title: "Metrics overview" },
  { id: "waveform", width: 12, title: "ECG waveform" },
];

export const CORE_CARD_IDS: readonly CoreCardId[] = CORE_CARDS.map(
  (card) => card.id,
);

export function isCoreCardId(value: string): value is CoreCardId {
  return (CORE_CARD_IDS as readonly string[]).includes(value);
}

export function defaultLayout(): LayoutItem[] {
  return CORE_CARDS.map((card) => ({
    id: card.id,
    kind: "core-card",
    title: card.title,
    width: card.width,
    hidden: false,
  }));
}

/* ------------------------------------------------------------------ *
 * 模块卡片
 * ------------------------------------------------------------------ */

export const MODULE_WIDGET_PREFIX = "module:";

export function widgetLayoutId(moduleId: string, widgetId: string): string {
  return `${MODULE_WIDGET_PREFIX}${moduleId}:${widgetId}`;
}

export function widgetSizeWidth(size: string): LayoutWidth {
  if (size === "sm") return 3;
  if (size === "lg") return 12;
  return 6;
}

export interface WidgetLayoutInput {
  id: string;
  title: string;
  width: LayoutWidth;
}

/**
 * 把当前已安装的模块卡片合并进布局：
 * - 已卸载的模块卡片被移除，未知 id 不进入渲染；
 * - 新出现的模块卡片插在「最近记录」之前，保持旧页面的视觉顺序。
 *
 * 模块列表还没加载完时不要调用（否则会误删已保存的模块卡片顺序）。
 */
export function mergeLayout(
  base: readonly LayoutItem[],
  widgets: readonly WidgetLayoutInput[],
): LayoutItem[] {
  const widgetIds = new Set(widgets.map((widget) => widget.id));
  const kept = base.filter((item) =>
    item.kind === "core-card"
      ? isCoreCardId(item.id)
      : widgetIds.has(item.id),
  );
  const present = new Set(kept.map((item) => item.id));
  const missing: LayoutItem[] = widgets
    .filter((widget) => !present.has(widget.id))
    .map((widget) => ({
      id: widget.id,
      kind: "module-widget",
      title: widget.title,
      width: widget.width,
      hidden: false,
    }));
  if (missing.length === 0) return [...kept];

  const recentIndex = kept.findIndex((item) => item.id === "recent");
  const insertAt = recentIndex === -1 ? kept.length : recentIndex;
  return [
    ...kept.slice(0, insertAt),
    ...missing,
    ...kept.slice(insertAt),
  ];
}

/* ------------------------------------------------------------------ *
 * 校验 / 迁移
 * ------------------------------------------------------------------ */

export type LayoutErrorCode =
  | "invalid_json"
  | "invalid_shape"
  | "empty"
  | "too_many"
  | "duplicate_id";

export class LayoutError extends Error {
  readonly code: LayoutErrorCode;

  constructor(code: LayoutErrorCode) {
    super(code);
    this.name = "LayoutError";
    this.code = code;
  }
}

const ITEM_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9:._-]*$/;
const KIND_VALUES: readonly LayoutItemKind[] = ["module-widget", "core-card"];

export function isLayoutWidth(value: unknown): value is LayoutWidth {
  return (
    typeof value === "number" &&
    (LAYOUT_WIDTHS as readonly number[]).includes(value)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeItem(value: unknown): LayoutItem | null {
  if (!isRecord(value)) return null;
  const { id, kind, title, width, hidden } = value;
  if (typeof id !== "string") return null;
  const trimmedId = id.trim();
  if (
    trimmedId.length === 0 ||
    trimmedId.length > LAYOUT_ID_MAX ||
    !ITEM_ID_PATTERN.test(trimmedId)
  ) {
    return null;
  }
  if (typeof kind !== "string" || !KIND_VALUES.includes(kind as LayoutItemKind)) {
    return null;
  }
  if (!isLayoutWidth(width)) return null;
  if (typeof hidden !== "boolean") return null;
  const trimmedTitle =
    typeof title === "string" ? title.trim().slice(0, LAYOUT_TITLE_MAX) : "";
  return {
    id: trimmedId,
    kind: kind as LayoutItemKind,
    title: trimmedTitle || trimmedId,
    width,
    hidden,
  };
}

export function parseLayout(raw: unknown): LayoutItem[] {
  let items: unknown[];
  if (Array.isArray(raw)) {
    items = raw;
  } else if (isRecord(raw) && Array.isArray(raw.items)) {
    items = raw.items;
  } else {
    throw new LayoutError("invalid_shape");
  }
  if (items.length === 0) throw new LayoutError("empty");
  if (items.length > LAYOUT_MAX_ITEMS) throw new LayoutError("too_many");

  const parsed: LayoutItem[] = [];
  const seen = new Set<string>();
  for (const entry of items) {
    const item = normalizeItem(entry);
    if (!item) throw new LayoutError("invalid_shape");
    if (seen.has(item.id)) throw new LayoutError("duplicate_id");
    seen.add(item.id);
    parsed.push(item);
  }
  return parsed;
}

type LayoutStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function getStorage(): LayoutStorage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    // 隐私模式 / 存储被禁用
    return null;
  }
}

/** 读取布局；任何异常都退回默认布局。 */
export function loadLayout(storage: LayoutStorage | null = getStorage()): LayoutItem[] {
  if (!storage) return defaultLayout();
  try {
    const raw = storage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return defaultLayout();
    const parsed = JSON.parse(raw) as unknown;
    if (isRecord(parsed) && "version" in parsed) {
      if (parsed.version !== LAYOUT_VERSION) return defaultLayout();
    }
    return parseLayout(parsed);
  } catch {
    return defaultLayout();
  }
}

/** 写入布局；条目先过校验，失败只抛错不写坏数据。 */
export function saveLayout(
  items: readonly LayoutItem[],
  storage: LayoutStorage | null = getStorage(),
): boolean {
  const validated = parseLayout([...items]);
  if (!storage) return false;
  try {
    storage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({ version: LAYOUT_VERSION, items: validated }),
    );
    return true;
  } catch {
    return false;
  }
}

export function clearSavedLayout(
  storage: LayoutStorage | null = getStorage(),
): void {
  try {
    storage?.removeItem(LAYOUT_STORAGE_KEY);
  } catch {
    // 存储不可用时无需处理
  }
}

/* ------------------------------------------------------------------ *
 * 导出 / 导入
 * ------------------------------------------------------------------ */

export function exportLayoutJson(items: readonly LayoutItem[]): string {
  return JSON.stringify({ version: LAYOUT_VERSION, items }, null, 2);
}

export function importLayoutJson(text: string): LayoutItem[] {
  let raw: unknown;
  try {
    raw = JSON.parse(text) as unknown;
  } catch {
    throw new LayoutError("invalid_json");
  }
  return parseLayout(raw);
}

/* ------------------------------------------------------------------ *
 * 宽度 → 栅格类
 * ------------------------------------------------------------------ */

/**
 * 页面用 `.eh-grid`（1 / 8 / 12 列）。desk 断点按 8 列折算，
 * 保证同一个「1–4 段」在两种宽度下都占同样比例。
 */
const WIDTH_CLASS: Record<LayoutWidth, string> = {
  3: "desk:col-span-2 xl:col-span-3",
  6: "desk:col-span-4 xl:col-span-6",
  9: "desk:col-span-6 xl:col-span-9",
  12: "desk:col-span-8 xl:col-span-12",
};

export function layoutWidthClass(width: LayoutWidth): string {
  return WIDTH_CLASS[width];
}

export function widthFromSegment(segment: number): LayoutWidth {
  if (segment === 1) return 3;
  if (segment === 2) return 6;
  if (segment === 3) return 9;
  return 12;
}

export function segmentFromWidth(width: LayoutWidth): number {
  if (width === 3) return 1;
  if (width === 6) return 2;
  if (width === 9) return 3;
  return 4;
}

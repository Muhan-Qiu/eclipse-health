/**
 * 与 eclipse-health.fit 网站共用的模块文案。
 *
 * 两份 JSON 由 `marketplace/site/module-copy.*.json` 同步而来，随 Vite 打包，
 * 运行时不发网络请求。文案按模块 ID 覆盖索引里的 name/description；
 * 找不到条目时所有调用方都会回退到索引字段。
 */
import enCopy from "./module-copy.en.json";
import zhCopy from "./module-copy.zh.json";

export interface ModuleCopyFeature {
  title: string;
  text?: string;
}

export interface ModuleCopyEntry {
  name?: string;
  tagline?: string;
  summary?: string;
  features?: ModuleCopyFeature[];
  usage?: string[];
  inputs?: string[];
  outputs?: string[];
  goodFor?: string;
  limits?: string[];
  techNote?: string;
}

interface ModuleCopyBundle {
  schemaVersion?: number;
  lang?: string;
  modules?: Record<string, ModuleCopyEntry>;
}

export type ModuleCopyLocale = "zh" | "en";

const BUNDLES: Record<ModuleCopyLocale, ModuleCopyBundle> = {
  zh: zhCopy as unknown as ModuleCopyBundle,
  en: enCopy as unknown as ModuleCopyBundle,
};

/** i18n 的语言标识（zh-CN / en-US）映射到文案 bundle。 */
export function copyLocaleFor(language: string | undefined): ModuleCopyLocale {
  return language?.startsWith("en") ? "en" : "zh";
}

export function getModuleCopy(
  language: string | undefined,
  moduleId: string,
): ModuleCopyEntry | undefined {
  return BUNDLES[copyLocaleFor(language)].modules?.[moduleId];
}

export const FIRST_PARTY_PREFIX = "org.eclipsehealth.";

/** 官方自研：ID 以 org.eclipsehealth. 开头，不依赖索引来源。 */
export function isFirstPartyModule(moduleId: string): boolean {
  return moduleId.startsWith(FIRST_PARTY_PREFIX);
}

export function moduleDisplayName(
  language: string | undefined,
  moduleId: string,
  fallback: string,
): string {
  return getModuleCopy(language, moduleId)?.name || fallback;
}

/** 与网站一致的官方自研排序：ECG 在前，睡眠在后。 */
const FIRST_PARTY_ORDER: Record<string, number> = {
  "org.eclipsehealth.relay-ecg": 0,
  "org.eclipsehealth.relay-sleep": 1,
};

export interface SortableMarketplaceModule {
  id: string;
  name: string;
  verified?: boolean;
}

/**
 * 排序：官方自研 → 已验证 → 名称。
 * 名称使用当前语言的本地化文案，官方自研内部沿用网站的固定顺序。
 */
export function sortMarketplaceModules<T extends SortableMarketplaceModule>(
  modules: readonly T[],
  language: string | undefined,
): T[] {
  const locale = copyLocaleFor(language) === "en" ? "en" : "zh-CN";
  return [...modules].sort((a, b) => {
    const aFirst = isFirstPartyModule(a.id);
    const bFirst = isFirstPartyModule(b.id);
    if (aFirst !== bFirst) return aFirst ? -1 : 1;
    if (aFirst) {
      const orderA = FIRST_PARTY_ORDER[a.id];
      const orderB = FIRST_PARTY_ORDER[b.id];
      if (orderA !== undefined || orderB !== undefined) {
        return (orderA ?? 99) - (orderB ?? 99);
      }
    }
    if (a.verified !== b.verified) return a.verified ? -1 : 1;
    return moduleDisplayName(language, a.id, a.name).localeCompare(
      moduleDisplayName(language, b.id, b.name),
      locale,
    );
  });
}

export interface SearchableMarketplaceModule {
  id: string;
  name: string;
  author?: string;
  description?: string;
}

/**
 * 市场搜索：名称、ID、作者、tagline、功能清单（标题 + 说明），
 * 同时保留索引里的描述与文案里的 summary，行为与网站一致。
 */
export function moduleMatchesQuery(
  module: SearchableMarketplaceModule,
  copy: ModuleCopyEntry | undefined,
  rawQuery: string,
): boolean {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return true;
  const parts: Array<string | undefined> = [
    module.id,
    module.name,
    module.author,
    module.description,
    copy?.name,
    copy?.tagline,
    copy?.summary,
    copy?.goodFor,
    ...(copy?.usage ?? []),
    ...(copy?.inputs ?? []),
    ...(copy?.outputs ?? []),
    ...(copy?.limits ?? []),
    ...(copy?.features ?? []).flatMap((feature) => [feature.title, feature.text]),
  ];
  return parts.some((part) => part?.toLowerCase().includes(query));
}

export const MODULE_DOCS_URL = "https://eclipse-health.fit/modules.html";

export function moduleDocsUrl(moduleId: string): string {
  return `${MODULE_DOCS_URL}?module=${encodeURIComponent(moduleId)}`;
}

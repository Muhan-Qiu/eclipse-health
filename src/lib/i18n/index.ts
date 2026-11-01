import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./zh-CN";
import enUS from "./en-US";

export const LOCALE_STORAGE_KEY = "eh-locale";
export const SUPPORTED_LOCALES = ["zh-CN", "en-US"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

const DEFAULT_LOCALE: AppLocale = "zh-CN";

function readStoredLocale(): AppLocale {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    return stored === "en-US" ? "en-US" : DEFAULT_LOCALE;
  } catch {
    // 隐私模式或存储被禁用时退回默认语言
    return DEFAULT_LOCALE;
  }
}

function applyDocumentLang(locale: string) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
}

const initialLocale = readStoredLocale();

void i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    "en-US": { translation: enUS },
  },
  lng: initialLocale,
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [...SUPPORTED_LOCALES],
  interpolation: { escapeValue: false },
  returnNull: false,
});

applyDocumentLang(initialLocale);
i18n.on("languageChanged", applyDocumentLang);

export function changeLocale(locale: AppLocale) {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // 忽略存储失败，语言在当前会话内仍然生效
  }
  void i18n.changeLanguage(locale);
}

/** 供 Intl 使用的 locale（i18n 可能返回 "zh-CN"/"en-US"）。 */
export function intlLocale(language: string | undefined): string {
  return language && language.startsWith("en") ? "en-US" : "zh-CN";
}

export default i18n;

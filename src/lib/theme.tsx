import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const THEME_STORAGE_KEY = "eh-theme";
export const PALETTE_STORAGE_KEY = "eh-palette";

export const PALETTES = [
  "a",
  "b",
  "c",
  "starry",
  "sunflower",
  "wave",
  "mist",
  "glaze",
] as const;
export type PaletteId = (typeof PALETTES)[number];
export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/** 玻璃主题需要半透明表面与 backdrop-filter；其余主题保持不透明。 */
export function isGlassPalette(palette: PaletteId): boolean {
  return palette === "mist" || palette === "glaze";
}

interface ThemeContextValue {
  mode: ThemeMode;
  resolved: ResolvedTheme;
  palette: PaletteId;
  glass: boolean;
  setMode: (mode: ThemeMode) => void;
  setPalette: (palette: PaletteId) => void;
  toggleMode: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function isPaletteId(value: string | null): value is PaletteId {
  return value !== null && (PALETTES as readonly string[]).includes(value);
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === "light" || value === "dark" || value === "system";
}

function readStoredMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeMode(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

function readStoredPalette(): PaletteId {
  try {
    const stored = localStorage.getItem(PALETTE_STORAGE_KEY);
    return isPaletteId(stored) ? stored : "a";
  } catch {
    return "a";
  }
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

/**
 * 自定义主题提供器（不用 next-themes）：
 * 它会在客户端渲染 <script>，React 19 会报 console error。
 * index.html 内联脚本负责首帧防闪烁，这里负责运行期切换与持久化。
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode);
  const [systemDark, setSystemDark] = useState(systemPrefersDark);
  const [palette, setPalette] = useState<PaletteId>(readStoredPalette);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      setSystemDark(event.matches);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolved: ResolvedTheme =
    mode === "dark" || (mode === "system" && systemDark) ? "dark" : "light";

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark");
    root.style.colorScheme = resolved;
  }, [resolved]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.palette = palette;
    if (isGlassPalette(palette)) {
      root.dataset.glass = "true";
    } else {
      delete root.dataset.glass;
    }
    try {
      localStorage.setItem(PALETTE_STORAGE_KEY, palette);
    } catch {
      // 存储不可用时配色仍在当前会话内生效
    }
  }, [palette]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // 忽略存储失败，点击后当前会话内仍然生效
    }
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      resolved,
      palette,
      glass: isGlassPalette(palette),
      setMode,
      setPalette,
      toggleMode: () => setMode(resolved === "dark" ? "light" : "dark"),
    }),
    [mode, resolved, palette, setMode],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useAppTheme must be used inside <ThemeProvider>");
  }
  return value;
}

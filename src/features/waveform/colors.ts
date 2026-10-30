/** 波形绘制用到的语义令牌；统一从 CSS 变量读取，避免写死颜色。 */
import { useEffect, useState } from "react";
import { useAppTheme } from "@/lib/theme";

export interface WaveColors {
  background: string;
  surface: string;
  signal: string;
  grid: string;
  border: string;
  muted: string;
  text: string;
  accent: string;
  warning: string;
  danger: string;
  success: string;
}

function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

export function waveColors(): WaveColors {
  return {
    background: token("--eh-bg", "#f7f5f1"),
    surface: token("--eh-surface", "#ffffff"),
    signal: token("--eh-signal", "#0f7c72"),
    grid: token("--eh-grid-line", "rgba(20,24,28,0.08)"),
    border: token("--eh-border-strong", "rgba(20,24,28,0.2)"),
    muted: token("--eh-text-muted", "#5e6974"),
    text: token("--eh-text", "#171a1d"),
    accent: token("--eh-accent", "#9a6a1e"),
    warning: token("--eh-warning", "#8a5a00"),
    danger: token("--eh-danger", "#b4363f"),
    success: token("--eh-success", "#2f7d32"),
  };
}

function sameColors(a: WaveColors, b: WaveColors): boolean {
  return (Object.keys(a) as (keyof WaveColors)[]).every((key) => a[key] === b[key]);
}

/**
 * 主题切换后延迟一帧读取令牌：
 * ThemeProvider 在 effect 里才改 `documentElement` 的 `.dark`，
 * 同一次 effect 里读取会拿到旧主题颜色，导致浅色卡片里残留深色波形。
 */
export function useWaveColors(): WaveColors {
  const { resolved, palette } = useAppTheme();
  const [colors, setColors] = useState<WaveColors>(() => waveColors());
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      setColors((previous) => {
        const next = waveColors();
        return sameColors(previous, next) ? previous : next;
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [resolved, palette]);
  return colors;
}

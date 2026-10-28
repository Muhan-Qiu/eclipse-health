import type { PaletteId } from "./theme";

/**
 * 配色预览色板，取自 docs/IDEAS.md 的莫奈三套配色。
 * 这些色值属于配色定义本身（用于设置页预览），不用于界面样式。
 */
export const PALETTE_PREVIEWS: Record<PaletteId, string[]> = {
  a: ["#1E2428", "#F4F0E8", "#8FA6B2", "#93A68F", "#4F6B6B"],
  b: ["#22262B", "#F5F1E9", "#7E97A8", "#D9B36C", "#3E5A6B"],
  c: ["#1C2124", "#F3EEE3", "#7C8B6B", "#C7A6A0", "#3F5F55"],
};

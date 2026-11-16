import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { realpathSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
// @ts-expect-error type error without @types/node package
import process from "node:process";
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(() => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
    // node_modules 在开发机上是指向上一版本目录的目录联接（junction）。
    // Vite 默认只允许工作区根目录内的文件；这里把真实路径加入白名单，
    // 否则 @fontsource 等从 node_modules 提供的字体在 dev 下会返回 403。
    fs: {
      allow: [
        fileURLToPath(new URL(".", import.meta.url)),
        realpathSync(fileURLToPath(new URL("./node_modules", import.meta.url))),
      ],
    },
  },
}));

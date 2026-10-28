# B2-04 · 桌面壳 + 品牌启动动画 + logo

> 难度：中等 2/4 · 建议思考强度：**medium**（Tauri 首次构建/插件卡住再升 high） · 批次：B2 贯通
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：让应用「像桌面应用」——单实例、托盘、窗口记忆、日食启动动画、正式 logo；不碰业务页面与后端。

## 1. 必读

- `docs/IDEAS.md`：Idea 001 全文（启动动画、logo 四版本、亮暗行为、减少动效）。
- `docs/UI_COMPONENT_SPEC_V1.md`：§0 原则、§1 令牌、§9 主题。
- `reports/B1-04-report.md`（现有主题/外壳/截图）。
- `src-tauri/tauri.conf.json`、`src-tauri/src/lib.rs`、`src-tauri/Cargo.toml`、`src/main.tsx`、`src/index.css`。

## 2. 必须先知道

- 仓库已初始化（私有本地，无 remote）；不要 commit/push，只读的 `git status` / `git diff` 可用。
- `uv` 不在 PATH；后端用 `backend\.venv\Scripts\python.exe -m uvicorn ...`。
- Tauri 1.x→2 的托盘 API 在 `tauri::tray`；窗口状态/单实例用官方插件。
- 首次 `cargo build` 可能 10 分钟以上，属正常；不要反复全量构建。
- `src/main.tsx` 与 `src/branding/**` 归你；**页面与设计令牌归 B2-03**，不要改。

## 3. 你必须交付

1. **Logo（品牌核心）**
   - 设计方向：深墨圆盘 + 一圈低饱和暖金/深青日冕光；16px 仍能识别「圆盘 + 环」。
   - **颜色必须走 `--eh-accent` / `--eh-signal` 等令牌**（或由令牌派生的 CSS 变量），不要写死 A/B/C 的具体色值；用户最终定配色后只换令牌。
   - 四版本：亮色、暗色、单色、favicon；SVG 源文件放 `public/brand/`；React 组件 `src/branding/Logo.tsx`（尺寸/变体 props）。
   - 用 1024×1024 PNG 跑 `npm run tauri icon <png>` 生成 `src-tauri/icons/*`；保留新 PNG 源。
   - 更新 `index.html` 的 title/favicon（你拥有该文件）。
2. **日食启动动画**
   - `src/branding/SplashScreen.tsx` + 自有 CSS（`src/branding/branding.css`），不要改全局令牌。
   - 暗色：背景保持 `#0A0C0F`，光环 40%→100%，名称淡入，主界面淡入。
   - 亮色：从黑开始，光环亮起，黑盘缩小淡出，背景过渡暖白 `#F7F5F1`，主界面淡入。
   - 约 1.6s；点击/按键可跳过；`prefers-reduced-motion` 降级为 300ms 淡入。
   - 在 `src/main.tsx` 用 `<SplashScreen>` 包裹现有 `<App/>`，不改变路由/Provider 结构；可加 `sessionStorage` 控制「每次启动播放」。
   - 若 Tauri 首帧白闪：优先 `tauri.conf.json` 窗口 `visible:false` + 前端 ready 后 show；仍不行再做独立 splash 窗口。把结论写报告。
3. **桌面行为**
   - 单实例：第二个实例聚焦已有窗口。
   - 托盘：图标 + 菜单（显示/隐藏、退出）；关闭窗口行为可配置（B2 先做「关闭到托盘」，菜单里真正退出）。
   - 窗口记忆：大小/位置/最大化恢复；最小 1080×700。
   - 主题跟随系统：前端已实现；Tauri 侧不要覆盖。
4. **后端 dev 启动（不打包）**
   - `src-tauri` 在 debug 下启动后端子进程：`../backend/.venv/Scripts/python.exe -m uvicorn eclipse_health_backend.app:app --port 8765`，cwd `../backend`；退出时结束子进程。
   - 已运行则复用（探测 127.0.0.1:8765），不要重复启动。
   - 生产打包（PyInstaller sidecar）留 B3；在 README/报告写清楚 dev 路径依赖。
5. **依赖**
   - 允许添加官方插件：`tauri-plugin-single-instance`、`tauri-plugin-window-state`（Rust crate + npm 包，版本与 Tauri 2 对齐）；托盘用核心 API，不需要插件。
   - 允许 `npm install` / `cargo add`，但只加这两个；报告版本。
6. **验证**
   - `npm run build` 通过。
   - `npm run tauri dev` 启动无 panic；托盘/单实例/窗口记忆各手动验证一次（写步骤）。
   - Playwright 截启动动画：`reports/screenshots/B2-04-splash-light.png`、`B2-04-splash-dark.png`（dev server 首屏 300–600ms 时截；必要时加 `?splash=hold` 调试参数）。
   - 若 Tauri 构建环境失败：保留 logo/动画成果，报告具体错误与已尝试项。

## 4. 文件所有权（只能改这些）

```
src/main.tsx
src/branding/**
public/brand/**
index.html
src-tauri/**
package.json            # 仅 Tauri 插件依赖
package-lock.json
```

不要动：`src/App.tsx`、`src/pages/**`、`src/components/**`、`src/lib/**`、`src/index.css`、`backend/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 与 B2-03 的契约

- 你包裹 `<App/>`；不改 App 内部、不改全局 CSS 变量。
- 你的样式只作用于 `src/branding/**`（类名前缀 `eh-brand-`）。
- 不替换侧栏 logo（B2-03 沿用现有标记）；如要统一，写进报告，验收后再做。

## 6. 验收命令

```powershell
npm run build
npm run tauri dev
```

报告写：logo 文件清单、启动动画时序、白闪处理结论、插件版本、Tauri 手动验证步骤、未完成项。

## 7. 明确不做

PyInstaller/安装包/自动更新（B3）、通知中心、开机自启、多语言切换（已有）、页面/波形/分析 UI、后端功能。

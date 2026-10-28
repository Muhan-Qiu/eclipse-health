# 报告 · B2-04 桌面壳 + 品牌启动动画 + logo

状态：完成（托盘「退出」与窗口记忆的“保存后重启恢复”需人工点一次确认；其余已自动验证）

## 交付

- Logo：`public/brand/logo-light.svg`、`logo-dark.svg`、`logo-mono.svg`（currentColor）、`favicon.svg`，以及图标源图 `public/brand/icon-1024.png`。
- 组件：`src/branding/Logo.tsx` 提供 `Logo`（size / variant: auto|light|dark|mono / decorative）与 `Wordmark`；颜色全部读 `--eh-logo-disk` / `--eh-logo-ring`（= `--eh-accent`），SVG 兜底值只是当前令牌值，换配色不用改 logo。
- Tauri 图标：`npm run tauri icon public/brand/icon-1024.png` 生成 `src-tauri/icons/*`（含 ico/icns），保留 1024 源图。
- 启动动画：`src/branding/SplashScreen.tsx` + `branding.css`；总 1600ms，暗色近黑底、光环 40%→100%、字标淡入；亮色从黑开始、黑盘缩小淡出（缩到 0.45 倍）、背景过渡到暖白、光环转墨色后淡出；点击/任意键跳过（200ms）；`prefers-reduced-motion` 只做 300ms 主界面淡入；sessionStorage 每次启动播一次，`?splash=1` 强制、`?splash=hold` 冻结关键帧（暗 950ms / 亮 1150ms）。
- `src/main.tsx`：`<SplashScreen>` 包裹 `AppProviders/App`，路由与 Provider 结构未变。
- 桌面行为（`src-tauri/src/lib.rs`）：单实例聚焦已有窗口；托盘（显示/隐藏/关闭时收起到托盘勾选项/退出），左键点托盘显示窗口；关闭窗口默认隐藏到托盘；窗口状态插件记忆大小/位置/最大化，最小 1080×700；主题仍由前端跟随系统，Tauri 不覆盖。
- dev 后端：debug 构建在 setup 里探测 127.0.0.1:8765，未运行则用 `backend/.venv/Scripts/python.exe -m uvicorn eclipse_health_backend.app:app --host 127.0.0.1 --port 8765`（cwd=backend）启动，退出时 `taskkill /PID <pid> /T /F` 结束整棵进程树（venv python 是启动器，单 kill 会遗留 uvicorn）；已运行则复用。路径用 `CARGO_MANIFEST_DIR` 解析，避免 cwd 不同导致找不到。生产 sidecar 留 B3。
- 白闪处理：窗口 `visible:false` + `backgroundColor:#0A0C0F`，页面 load 后 Rust 侧 show（12s 兜底），`index.html` 首帧内联近黑底。dev 启动未观察到白闪；若 B3 仍有，再改独立 splash 窗口。
- `index.html`：favicon 指向 `/brand/favicon.svg`，加 apple-touch-icon、双 theme-color、近黑首帧底色；标题保持 `eclipse health`。

## 验证

- `npm run build`：pass（tsc + vite，约 1.9s；产物 762 kB / gzip 246 kB，仅有 >500 kB 提示，非本批范围）。
- `cargo check` / `cargo build`：pass，冷启动 10m09s，增量 12–26s，0 warning；tauri 2.12.5。
- `npm run tauri dev`：启动无 panic。因并行 Agent 占用 1420，本次用
  `npm run tauri dev -- --config '{"build":{"beforeDevCommand":"","devUrl":"http://localhost:1420"}}'`
  复用现有 Vite；窗口 “eclipse health”，后端自动启动，前端 `/api/v1/records` 返回 200。
- 单实例：再启动一个 `v3.exe` → 立即退出（HasExited=true），只剩 1 个进程，原窗口保留。
- 关闭到托盘：`CloseMainWindow()` 后进程仍存活、主窗口从窗口列表消失；再启动第二个实例 → 主窗口重新显示。
- 后端复用：手动起 uvicorn 后再启动应用，日志 `[dev] backend already listening ..., reusing it`，无第二个进程。
- Playwright（复用 1420）：300ms 时遮罩+主界面动画存在，2200ms 后卸载；主界面 DOM 节点在动画前后保持同一实例（不重挂载 Provider）；点击 350ms 内跳过（早跳过走 300ms 淡入）；同会话重载不再播放；模拟 `prefers-reduced-motion` 时不渲染遮罩、主界面 300ms 淡入。截图：`B2-04-splash-light.png`、`B2-04-splash-dark.png`、`B2-04-logo-variants.png`（四版本亮/暗对照）、`B2-04-light-app-check.png`（启动后亮色主界面）；品牌相关 0 console error（仅后端未启动时的 8765 连接报错，属并行区）。

## 未做 / 偏离

- 未改 README（不在文件所有权内）；dev 路径依赖见上文。
- npm 侧未加插件包：托盘/窗口/单实例全部走 Rust API，无需 JS 权限，`capabilities/default.json` 未改。
- 插件版本：`tauri-plugin-single-instance` 2.5.5、`tauri-plugin-window-state` 2.5.0（`cargo add` 取 2.x 最新）。
- “关闭到托盘”配置做进托盘勾选菜单，没有设置页 UI（设置页属 B2-03）。
- 托盘菜单文案为原生中文，不走 i18n。
- `cargo fmt` 未运行：本机 stable 工具链未装 rustfmt，代码手工按 rustfmt 风格对齐。
- 窗口记忆的“保存→重启恢复”需要托盘「退出」触发，无法用脚本点击托盘，留人工步骤 2；后端退出清理逻辑（taskkill /T）已用同命令单独验证。
- 本批验证期间并行 Agent 的 `useImport must be used inside <ImportProvider>` 曾导致 Dashboard/Records 崩溃、页面全黑，后随其代码更新消失；如复现请找对应 Agent，不是品牌层问题。

## 跨区需求（需要别的 Agent 或指挥官处理）

- 侧栏左上仍是旧标记；是否统一换成 `Logo` 组件由 B2-03 验收后决定（本批按契约未动）。
- B3 打包需把 dev 子进程替换为 PyInstaller sidecar，并确认首帧仍无白闪。

## 需要指挥官决策

- 配色 A/B/C 定稿；定稿后启动动画与 logo 会自动跟随令牌，无需改 SVG。
- 关闭窗口默认“收起到托盘”是否符合预期（托盘菜单可即时切换）；是否要在设置页暴露该开关与启动动画开关。
- `?splash=1` / `?splash=hold` 调试参数是否长期保留。

## 建议下一批

- B3：sidecar 打包、自动更新、安装包图标校验。
- 设置页加“关闭到托盘 / 启动动画”开关（需新增 i18n key），侧栏换新 logo。

## 人工验证步骤

1. `npm run tauri dev` → 托盘出现 logo；左键点图标显示窗口，右键菜单含 显示/隐藏/关闭时收起到托盘/退出。
2. 拖动并缩放窗口 → 托盘「退出 eclipse health」→ 重新启动 → 大小/位置恢复，且不能再缩到 1080×700 以下。
3. 点窗口关闭按钮 → 窗口隐藏、进程仍在；托盘「退出」→ 进程结束，`netstat -ano | findstr :8765` 无监听（后端一并结束）。
4. 启动第二个实例 → 不出现新窗口，原窗口前置获得焦点。
5. 浏览器：`localhost:1420/?splash=1` 强制重播；`?splash=hold` 冻结暗/亮关键帧，点击继续。

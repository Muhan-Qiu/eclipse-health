# 报告 · B1-04 UI 外壳与设计系统

状态：完成

## 交付

- 设计令牌 `src/index.css`：`--eh-*`（背景/卡片/描边/文字/accent/signal/五个语义色）、字体栈、间距 4–64、圆角 8/12/16/24、动效 120/200/320ms；shadcn 变量全部映射到 `--eh-*`，组件不写死颜色。
- 主题：light（暖白）/dark（近黑），默认跟随系统；`html.dark` + `html[data-palette]`。三套莫奈配色 A 睡莲 / B 日出·印象 / C 日本桥，默认 A；首帧内联脚本防闪烁。
- 应用外壳 `src/components/layout/`：可折叠侧栏（折叠后图标 + tooltip）、顶部上下文栏、内容区最大 1440 / 外边距 32 / 12 列网格（≥1280 12 列、≥960 8 列、<960 单列，`--breakpoint-desk`）。
- 路由（HashRouter）：`/` 仪表盘、`/records`、`/records/:id`、`/trends`、`/reports`、`/assistant`、`/settings`、`/modules`、`/about`、`*` 404。
- 页面：仪表盘（问候/日期 + 3 张引导卡 + 最近记录 + 指标概览示例卡 + 合成波形卡 + 支持格式弹窗）；记录页（时间/设备/标签筛选 + 空状态 + 无匹配状态）；设置（主题/配色/语言/版本）；模块（3 张静态占位卡）；趋势/报告/助手占位；关于；404。
- 命令面板 `Ctrl+K`（cmdk）：全部页面、主题（亮/暗/跟随系统）、三套配色、关于；分组展示，键盘可用，窄窗口下高度自适应。
- i18n `react-i18next`：`zh-CN` 默认、`en-US` 备用，全部可见文案走 key，日期/数字用 `Intl`；语言持久化。
- Mock 层 `src/lib/api/`：`health()`、`records.list()`、`records.get()`、`records.analysis()`；dev 默认 mock（`VITE_USE_MOCK` 可覆盖），3 条合成记录 + 1 条合成分析；所有示例数据带「示例」徽标。
- 可访问性：跳转链接、`aria-label`/`aria-pressed`/`aria-expanded`、2px accent focus ring、减少动效降级、异常不只靠颜色；对比度实测全部 ≥4.5:1（正文）/≥3:1（图形）。
- 加载骨架 + 页面淡入（200ms，尊重 `prefers-reduced-motion`）。

## 验证

- 命令：`npm run build` → pass（tsc + vite，750ms；产物 JS 599.74 kB / gzip 189.81 kB，有 >500 kB 提示）。
- 命令：`npm run dev`（1420）+ Playwright 全路由巡检 → 0 console error（信息级日志除外）。
- 截图（`reports/screenshots/`）：`B1-04-light-1440.png`（1440×1100）、`B1-04-dark-1440.png`（1440×1100）、`B1-04-light-1080.png`（1080×700）、`B1-04-palette-b.png`（1440×1100，亮色 + 配色 B）。
- 交互实测：配色切换、主题切换、语言切换均即时生效并写入 localStorage；1080×700 无横向溢出、侧栏不塌。

## 未做 / 偏离

- 未做启动日食动画、正式 logo、真实波形交互、记录详情数据、模块安装、LLM、PDF（按范围属 B2）。
- 用 HashRouter 而非 BrowserRouter：Tauri asset 协议不做 SPA 回退，避免打包后刷新 404。
- 未使用 next-themes 的 Provider：它会在客户端渲染 `<script>`，React 19 报 console error；自写 ThemeProvider（同一 `eh-theme` 存储键）。`ui/sonner` 仍 import next-themes 的 `useTheme`，Toaster 由外层显式传 `theme`。
- 修复了 shadcn 生成的 `ui/command.tsx`：`CommandDialog` 缺少 `<Command>` 包裹导致 cmdk 崩溃。
- 仪表盘「最近记录」在 mock 下显示 3 条记录；无数据时显示空状态（记录页可复现空/无匹配两种状态）。
- 未接入 fetch 缓存/重试之外的后端特性；`records.analysis()` 目前只给 mock，页面未消费。

## 跨区需求（需要别的 Agent 或指挥官处理）

- 后端需提供 `GET /api/v1/health`、`GET /api/v1/records`、`GET /api/v1/records/{id}`，字段与 `src/lib/api/types.ts` 的 `RecordSummary` 对齐（camelCase；`device.vendor|model`、`tags`、`leads`、`sampleRateHz`、`status`）。若 B1-01 用 snake_case，需要一个映射层，请指挥官定。
- Tauri 窗口最小 1080×700、标题/图标属 `src-tauri/tauri.conf.json`（B2，不在本批所有权内）。
- 打包产物 600 kB 提示：如需消除，建议 B2 做路由级 `React.lazy` 或调整 chunk 阈值（`vite.config.ts` 不属本批）。

## 需要指挥官决策

- 生产构建（无后端）目前不走 mock，打开会显示「加载失败」。B2 接通前是否让 `VITE_USE_MOCK` 在 build 下也默认 true？
- 配色 A/B/C 的最终选择（设置页可实时预览）；定稿后同步替换 `docs/UI_COMPONENT_SPEC_V1.md` 的颜色表。

## 建议下一批

- B2 接后端记录/分析 API，补记录详情、真实波形（uplot）与导入拖拽；启动动画与 logo 四版本；Tauri 侧栏宽/窗口记忆；路由懒加载。

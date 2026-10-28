# B1-04 · UI 外壳与设计系统

> 难度：中等 2/4 · 建议思考强度：**medium** · 批次：B1 地基
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 这一批不接真后端、不做波形交互、不做启动动画；只把「空壳」做成有品质、可扩展、亮暗都好看的应用骨架。

## 1. 必读

- `docs/UI_COMPONENT_SPEC_V1.md`：§0 原则、§1 令牌、§2 布局、§3 组件集、§6 页面/导航/命令、§7 图表、§8 可访问性、§9 主题。
- `docs/IDEAS.md`：Idea 001 的莫奈三套配色与 logo 方向。
- `docs/V3_FEATURE_BACKLOG.md`：A1–A6、C2、H2（本批只做外壳与空状态，不实现分析）。
- `src/index.css`、`src/App.tsx`、`components.json`、`tsconfig.json`。

## 2. 已知基线问题

`npm run build` 当前失败：

```
tsconfig.json(16,5): error TS5101: Option 'baseUrl' is deprecated ... TypeScript 7.0
```

请用最小改动修复（TS 6 下 `paths` 可不需要 `baseUrl`，或加 `ignoreDeprecations`；选干净方案并说明）。修完 `npm run build` 必须通过。

## 3. 你必须交付

1. **设计令牌层**
   - `--eh-*` 语义令牌：背景/次级背景/卡片/浮层/描边/主文字/次级文字/accent/signal/danger/warning/success/info。
   - 两套主题：light / dark；默认跟随系统，无法判断时用 light（暖白主界面）。
   - 三套莫奈配色 A 睡莲 / B 日出·印象 / C 日本桥（色值见 `docs/IDEAS.md`），通过 `data-palette="a|b|c"` 切换，默认 A。
   - 字体栈：标题衬线（Source Han Serif SC / Noto Serif SC / Songti SC），正文无衬线（Inter / Noto Sans SC / system-ui），数字等宽（Geist Mono / JetBrains Mono）。不新增字体依赖。
   - 间距 4/8/12/16/20/24/32/40/48/64；圆角 8/12/16/24；动效 120/200/320ms，尊重 `prefers-reduced-motion`。
   - 不得写死颜色到组件里；所有组件只用令牌。
2. **应用外壳**
   - 左侧可折叠导航 + 顶部上下文栏 + 内容区；最大宽度 1440，外边距 32；12 列网格。
   - 路由（React Router）：`/` 仪表盘、`/records` 记录、`/records/:id` 详情占位、`/trends` 趋势占位、`/reports` 报告占位、`/assistant` 助手占位、`/settings` 设置、`/modules` 模块占位、`/about` 关于。
   - 导航图标用 Lucide；当前项有清晰状态；折叠后只留图标 + tooltip。
   - 窗口最小 1080×700 不塌；≥1280 12 列、≥960 8 列、<960 单列。
3. **页面内容（B1 只做骨架与空状态）**
   - 仪表盘：顶部问候/日期；3 张引导卡（导入 ECG / 看示例记录 / 支持格式）构成 A3 空状态；一个「最近记录」空列表骨架；一个「指标概览」演示卡（合成数据，明确标注「示例」）；一个合成 ECG 波形缩略卡（SVG/canvas 折线即可，标注「示例」）。
   - 记录页：筛选栏（时间/设备/标签，禁用或本地状态）+ 空状态。
   - 设置页：外观（亮/暗/跟随系统 + 三套配色预览选择）、语言（中文/English）、关于版本；选择持久化到 localStorage。
   - 模块页：说明「模块系统即将上线」，展示 2–3 张静态占位卡（导入器/分析模型/主题），不要做安装逻辑。
   - 其余页面：统一的 PageHeader + 空状态 + 说明，不要留白板。
   - 加载骨架（A5）与页面淡入过渡；不要过度动效。
4. **命令面板**
   - `Ctrl+K` 打开（cmdk），可跳转所有页面、切换主题/配色、打开「关于」；空查询时分组展示；键盘可用。
5. **国际化**
   - `react-i18next`，`zh-CN` 默认、`en-US` 备；所有可见文案走 key；日期/数字用 `Intl`。
   - 语言选择持久化。
6. **Mock 数据层**
   - `src/lib/api/client.ts`：base `http://127.0.0.1:8765/api/v1`，先实现 `health()` 和 `records.list()`；`VITE_USE_MOCK=true`（默认 dev）时走本地 mock。
   - mock 数据：3 条合成记录（不同日期/设备/标签）+ 1 条合成分析摘要；**不得**伪造真实患者信息或诊断结论。
   - TanStack Query 配置在 `src/app/providers.tsx`；不要为每个页面写一套 fetch。
7. **可访问性**
   - 键盘可达、focus ring 可见、对比度 AA、图标按钮有 aria-label、减少动效降级、色盲友好（异常不只靠颜色）。
8. **验证与截图**
   - `npm run build` 通过；`npm run dev` 无 console error。
   - 用 Playwright（项目 MCP 或 `webapp-testing` skill）截 4 张图到 `reports/screenshots/`：
     - `B1-04-light-1440.png`、`B1-04-dark-1440.png`、`B1-04-light-1080.png`、`B1-04-palette-b.png`。
   - 截图要等字体与动画稳定后再截。

## 4. 文件所有权（只能改这些）

```
src/**
index.html
package.json          # 仅必要时；依赖基本已齐
tsconfig.json         # 仅修 TS5101
```

不要动：`src-tauri/**`、`backend/**`、`docs/**`、`prompts/**`、`uploads/**`、`vite.config.ts`（除非端口/别名确实要改，先在报告说明）。不要引入新的 UI 框架、图标库、状态库、CSS-in-JS。

## 5. 设计方向（硬约束）

- 安静、临床可信、典雅；信息优先，装饰克制。
- 禁止：高饱和渐变、玻璃拟态堆叠、霓虹发光、夸张阴影、满屏动效、圆角过大。
- 标题可用衬线，正文无衬线；数字用等宽、tabular-nums；单位与来源要清楚。
- 亮色以暖白为主，暗色近黑；accent 低饱和暖金/深青，波形用低饱和青绿。
- 所有「示例/演示」数据必须显式标注，不能与真实记录混淆。
- 不要复制 Apple Health / Oura 的素材；只参考信息架构。

## 6. 验收命令

```powershell
npm run build
npm run dev
```

报告写：build 结果、4 张截图路径、路由清单、令牌/配色切换方式、未接真后端的部分、B2 需要接的 API。

## 7. 明确不做

启动日食动画与 logo（B2）、真实波形交互（B2）、记录详情/趋势/报告的真实数据、模块安装 UI、LLM 助手、PDF、Tauri 托盘/窗口记忆（B2）、后端代理与 sidecar。

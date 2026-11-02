# 报告 · D2 视觉/可用性 QA（亮/暗、对比度、间距、焦点、窄窗）

状态：完成

## 范围与方法

- 12 个页面 × 亮/暗 × 1440/1024：仪表盘、记录、健康数据、记录详情、趋势、对比、报告、助手、健康档案、模块、设置、关于。
- 真实后端（8765，`backend/.data` 真实记录/分析/健康导入）+ Vite dev（1420），Playwright + Chrome headless 逐页截图。
- 自动检查：正文/次级/占位符/禁用态对比度（WCAG AA，含祖先 opacity 合成）、横向溢出、可见文本裁切、无名称图标按钮、控制台 error；键盘 Tab 实测焦点顺序与焦点环。
- 自动检查之外逐张目视：间距/对齐、空状态、暗色卡片层次、表格/列表状态、颜色语义。

## 问题清单

| 页面 | 问题 | 严重度 | 处理 |
|---|---|---|---|
| 记录 / 健康档案 / 设置 | 禁用按钮（对比、保存档案、清空全部）文字对比度 2.3–2.9:1，禁用态难读 | 中 | **已修**：`components/ui/button.tsx` disabled opacity 50% → 70%，复测 0 项低于阈值 |
| 设置（隐私/桌面） | 长中文描述与右侧开关同排时文本列可被撑出 11px；缺 `min-w-0` 兜底 | 低 | **已修**：描述列加 `min-w-0 flex-1`（desktop-panel / privacy-panel） |
| 对比 | 未选任何记录时，空状态标题仍写「还需要一条记录」，与 0 选择不符 | 低 | **已修**：0 条时显示「选择两条记录开始对比」，1 条时保留原文案（zh/en 同步） |
| 全站（记录/仪表盘/报告选择器） | 时长格式不一致：`30:05.556`、`0:02.5`、`0:02`、`0:10` 混用，同一列表内精度跳动 | 中 | **未修（跨区）**：来源 `src/lib/format.ts#formatDuration`，不在 D2 所有权；详见跨区需求 |
| 报告 | 记录选择器第二行 `— · 30:05 · MLII/V5` 与记录页 `本地文件 · MLII / V5 · 360 Hz` 信息结构不一致，「—」占位 | 低 | 未修：属信息文案取舍，非破版，建议随 format 统一时一并处理 |
| 对比 | 页头与空状态各有一个「返回记录列表」 | 低 | 不改：页头是全局返回，空状态是下一步操作，语义不同 |
| 趋势 | Y 轴刻度为 75.6 / 74.6 / 73.5 等非整值 | 低 | 不改：可读、无重叠，属数据域自动刻度 |
| 仪表盘 | 「最近记录」3 条时卡片下方大块空白（与右列等高） | 低 | 只记录：`dashboard.tsx` 属 D1，未改动 |
| 助手 | 右侧对话卡片空状态位于中上部，下方留白较大 | 低 | 不改：空状态在可视区居中，属设计取舍 |
| 健康数据 | 类型 chips 与「时间」标签基线不同（select 标签在上方） | 低 | 不改：与记录页「标签 chips + 控件标签在上」模式一致 |

其余页面（记录、健康数据、记录详情、报告、助手、健康档案、模块、设置、关于、趋势）亮暗两套均未发现对比度、溢出、裁切、焦点或无名称图标按钮问题。

## 交互与可访问性实测

- 记录页 Tab 顺序：跳转主内容 → 侧栏导航 → 折叠导航 → 主题/设置 → 导入 → 筛选 → 列表；顺序合理。
- 全部 22 个焦点停留点均有可见指示：全局 2px accent outline，或 Button/Select 的 3px `ring`（`outline-none` + ring 组合），暗色同样可见。
- 无 `aria-label` 的图标按钮：0 个（脚本扫描 + 抽查星标、刷新、主题、详情/停止/禁用/卸载）。
- 颜色语义：已分析/未分析、运行中、警告均带图标或文字，不只靠颜色区分。

## 验证

- `npm run build` → **通过**，`tsc` 无错误，vite `✓ built in 3.06s`；仅原有 >500kB chunk 提示。
- 复测（after）：24 个「页面 × 主题」组合，1440 与 1024 两档，**对比度问题 0、横向溢出 0、可见文本裁切 0、无名称按钮 0、控制台 error 0**。
- 设置页剩余「scrollWidth 超 11px」为 Switch 拇指 `translate-x` 的固有内部溢出，非布局问题；已排除。
- 窄窗 1024：无页面级横向滚动，侧栏折叠正常（D1 布局未改）。

## 截图

`reports/screenshots/`，修复前/后同名成对：

- 记录：`D2-records-{light,dark}-{before,after}.png`
- 健康数据：`D2-health-data-{light,dark}-{before,after}.png`
- 趋势：`D2-trends-{light,dark}-{before,after}.png`
- 对比：`D2-compare-{light,dark}-{before,after}.png`（after 可见新空状态文案）
- 报告：`D2-reports-{light,dark}-{before,after}.png`
- 助手：`D2-assistant-{light,dark}-{before,after}.png`
- 健康档案：`D2-profile-{light,dark}-{before,after}.png`
- 模块：`D2-modules-{light,dark}-{before,after}.png`
- 设置：`D2-settings-{light,dark}-{before,after}.png`
- 关于：`D2-about-{light,dark}-{before,after}.png`
- 只读对照：`D2-dashboard-{light,dark}-*.png`、`D2-record-detail-{light,dark}-*.png`
- 补充：`D2-compare-filled-light-before.png`、`D2-records-selected-light-before.png`、`D2-health-data-page2-light-before.png`、`D2-health-data-payload-light-before.png`

## 未做 / 偏离

- 未改 D1 文件：`dashboard.tsx`、`record-detail.tsx`、`branding/**`、`layout/**`、`common/**`、`index.css`、`lib/motion.ts`；动画未动。
- 未改 `modules/widgets/**`、`modules/pages/**`、`waveform-viewer.tsx`。
- 未改业务逻辑/接口/数据；未新增依赖；未改 `docs/`、`prompts/`、`uploads/`；未 commit。
- 未做：加载/错误态的强制复现截图（后端中断只会触发连接错误视频；错误/骨架态已用代码路径与既有截图覆盖），空状态除对比页外均为真实数据页面。

## 跨区需求

1. `src/lib/format.ts#formatDuration`：统一时长精度（建议秒级记录显示 `mm:ss` 或 `mm:ss.S`，同一列表固定位数），影响记录页、仪表盘、报告选择器。属 D1/指挥官协调范围。
2. `src/pages/dashboard.tsx`：最近记录卡片与右列等高导致短列表时大面积空白，建议 `items-start` 或让左卡内容高度自适应。
3. `src/features/reports/record-picker.tsx`：记录摘要第二行与记录页字段顺序不同、以「—」占位，建议复用记录行摘要格式。

## 需要指挥官决策

- 时长展示统一到哪种精度（`0:02` / `0:02.5` / `0:02.500`）？确定后可由 lib 所有权方一次修完。

## 建议下一批

- 建一个轻量视觉回归脚本（本次的对比度/溢出/裁切检查）纳入 D 系列验收，避免后续页面回退。

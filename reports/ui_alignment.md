# A1 · 桌面端 UI 对齐报告

分支：`feat/ui-alignment`
日期：2026-11-01

## 1. 审计方式

- 用 Vite dev server + Playwright，在 **1024 / 1280 / 1440 / 1920** 四个宽度逐页截图并量取 DOM 矩形。
- 覆盖：`/`、`/records`、`/records/:id`、`/health-data`、`/trends`、`/compare`、`/reports`、`/modules`、`/assistant`、`/settings`、`/profile`，以及导入弹窗、模块安装弹窗、dashboard 编辑模式。
- 截图：`reports/ui-alignment/before/`（修改前）与 `reports/ui-alignment/after/`（修改后）。
- 量取项：`document.documentElement.scrollWidth`、`main.scrollWidth`、同一 CSS Grid 行内每张卡片的 `top/bottom/width`、弹窗 `scrollWidth/clientWidth`。

## 2. 根因

1. **卡片在栅格里不拉伸**（最主要）
   - 仪表盘 `LayoutGrid` 给每张卡套了一层 `<div class="min-w-0">`，栅格项被拉伸到行高，但里面的 `Card` 仍是自然高度。
   - 结果：9+3 的「健康评分 / 健康建议」底边相差 54px，6+6 的「最近记录 / 指标概览」相差 3px。
   - 记录详情左侧波形 `Card` 也停在内容高度，右侧分析栏却到行底，实测相差 **645px**。
2. **编辑模式与浏览模式宽度不一致**
   - 编辑模式的栅格单元带 `border + p-2`，卡片被吃掉了 16px 宽度，左右位置也与浏览模式错开。
3. **双栏/多栏没有统一高度策略**
   - 助手页左栏 `desk:col-span-3`（1024 下约 269px）里塞了带两个操作按钮的卡片头，标题被挤成逐字换行，长按钮被裁切。
   - 报告页右侧「报告历史」不随左栏拉伸，两栏底边相差约 740px。
4. **长文本被挤到只剩省略号**
   - `RecordRow` 的日期是 `flex-wrap` 行里的 `truncate`，无 `shrink-0`，1024 下日期被压成 `2026...`。
5. **弹窗在 768 下贴边**
   - 模块安装弹窗的 `sm:max-w-4xl` 覆盖了基础 `max-w-[calc(100%-2rem)]`，768 宽度下弹窗左右正好贴住视口（left 0 / right 768）。
6. **筛选栏基线不齐**
   - 记录页标签筛选组、健康数据页类型筛选组没有与「标签 + 控件」的 56px 控件带同高，chips 贴在底部。
7. **设置页出现半行空洞**
   - 1024（8 列）下「外观」占满整行后，「语言」只有 4/8 列且独占一行，右侧半行空白。

## 3. 修改文件与内容

| 文件 | 修改 |
|---|---|
| `src/index.css` | `.eh-grid` 显式 `align-items: stretch`、子项 `min-width: 0`；新增 `.eh-layout-cell`（纵向 flex，卡片 `flex: 1`）供仪表盘栅格使用 |
| `src/components/ui/card.tsx` | Card 根节点加 `min-w-0`，长标题不再撑破栅格列 |
| `src/features/layout/layout-editor.tsx` | 浏览/编辑模式统一改用 `.eh-layout-cell`；编辑模式去掉 `border + p-2`，改用不占布局的 `outline`，卡片宽度与浏览模式完全一致；隐藏占位块 `flex-1` |
| `src/pages/dashboard.tsx` | 三列引导卡 `h-full`，描述 `flex-1`，操作区改 `mt-auto pt-4`，按钮贴底 |
| `src/pages/record-detail.tsx` | 左栏改 `flex flex-col` + 卡片 `flex-1`；隐私说明移入卡片内部，左右两栏卡片底边对齐；右栏 `min-w-0` 且卡片 `flex-1` |
| `src/features/assistant/assistant-workspace.tsx` | 1024 下左栏/右栏都改为整行堆叠，1280 起才 4+8 双栏；左栏改 `flex flex-col gap-4` |
| `src/features/assistant/session-list.tsx` | 新增 `className`，卡片 `h-full`，内容区 `flex-1 overflow-y-auto`，与右侧对话卡底边对齐 |
| `src/features/reports/reports-workspace.tsx` | 去掉 `lg:items-start`，两栏默认拉伸；左侧加 `min-w-0` |
| `src/pages/settings.tsx` | 语言卡 `desk:col-span-8 xl:col-span-4`，消除 1024 下半行空白 |
| `src/pages/profile.tsx` | `MetricsPanel` 的 `desk:col-span-12`（8 列网格里跨 12 列）改为 `desk:col-span-8 xl:col-span-12` |
| `src/pages/records.tsx` | 标签筛选组加 `min-h-14`，与「标签 + 下拉」的 56px 控件带对齐 |
| `src/pages/health-data.tsx` | **只改布局类名**：类型筛选组加 `min-h-14`；未触碰导入流程、接口、文案 |
| `src/components/records/record-row.tsx` | 日期加 `shrink-0`，完整显示；超长摘要仍按原规则省略 |
| `src/features/modules/install-dialog.tsx` | 安装弹窗加 `w-[calc(100%-2rem)] sm:max-w-4xl`，768 下左右各留 16px，不再贴边 |

## 4. 验收结果

- `npm run build`：通过（`✓ built in 7.11s`，TS + Vite）。
- **1024 宽度无横向滚动**：全部 11 个页面与导入/安装弹窗实测 `docOverflow = 0`、`mainOverflow = 0`；768 下同样为 0。
- **同排卡片底边对齐**（实测 `bottom`）：
  - 1024：`scores/suggestions = 695/695`，`recent/metrics = 1442/1442`；引导卡 `208/208/208`。
  - 1280/1440：`595/595`、`1257/1257`；引导卡 `208/208/208`。
  - 1920：`595/595`、`1257/1257`；引导卡 `188/188/188`。
  - 顶部位置差 `topSpread = 0`。
- **编辑模式与浏览模式宽度一致**：1024/1280/1440 下六张卡的 `width` 差值和 `left` 差值全部为 **0**；编辑模式每行卡片底边也一致。
- **弹窗**：768 下安装弹窗 736px（左右 16px），导入弹窗 672px（左右 48px），`scrollWidth === clientWidth`。
- **Console**：无 JS 异常 / React 报错。仅有两类网络 404（见第 6 节），由未启动的后端接口造成，与布局改动无关。

## 5. 仍未对齐 / 已知取舍

1. **编辑模式行高比浏览模式高**：每张卡上方多出标题 + 宽度/显隐/排序控制条，行高必然增加。卡片宽度、间距、同排底边已完全一致，但「编辑 ↔ 浏览」的绝对行高无法相同。
2. **1024 下 3/12 窄卡（健康建议、模块小卡）**仍只有约 168px，内容会正常换行/省略；这是 9+3 比例本身决定的，未改栅格比例。
3. **仪表盘「最近记录」卡片在 1024 下半宽时**，设备型号等次要文字会省略；日期已完整显示，完整信息在 `/records` 可见。
4. **报告页右侧历史栏**现在会拉伸到与左栏同高，空状态时下半部分留白；这是两栏底边对齐的直接结果。
5. **健康数据页工具栏**只做了控件带高度对齐；导入流程、状态机、接口均未触碰。

## 6. 环境备注

- 本次用 `VITE_USE_MOCK=true` 启动前端；后端未启动时，`/reports` 与助手供应商预设会向 `127.0.0.1:8765` 发出 404 请求（浏览器记为 “Failed to load resource”）。这些不是 JS 运行时错误，后端启动后消失。
- 截图目录：
  - `reports/ui-alignment/before/`：dashboard 1024/1440、records、record-detail、health-data、trends、compare、reports、modules、assistant、settings、profile。
  - `reports/ui-alignment/after/`：同上，另含 dashboard 1280/1920、编辑模式、导入/安装弹窗 768/1024。

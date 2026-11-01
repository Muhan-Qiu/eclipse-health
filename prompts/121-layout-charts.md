# H2 · 布局编辑 + 声明式图表类型（bar/line/heatmap）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md`、`docs/UI_COMPONENT_SPEC_V1.md`、`src/pages/dashboard.tsx`、`src/features/modules/widgets/**`。
> **思考强度：low。** 不引入 ECharts/uPlot；全部用 SVG/CSS + 现有令牌。

## 交付

### 1. 声明式图表类型

- `schemas/module.schema.json`：`widgetView.type` 增加 `bar | line | heatmap`：
  - `bar`/`line`：`valuePath` 指向数字数组，或 `seriesPath` + `labelPath`；
  - `heatmap`：`valuePath` 指向 `[{date,value}]` 或二维数组；
  - 保持现有 `stat/sparkline/list/progress/text` 兼容；未知类型降级。
- `src/features/modules/widgets/widget-view.tsx`：用 SVG/CSS 渲染三种新图：
  - 颜色走 `--eh-accent`/图表令牌；亮暗可读；
  - 空数组/全 null 显示「暂无数据」；
  - 不做第三方图表库；无动画或复用现有 600ms 绘制。
- `docs/MODULE_CONTRACT_V2.md` 补字段与示例。

### 2. 布局编辑

- 新建 `src/features/layout/`：
  - `layout.ts`：布局项 `{id, kind:"module-widget"|"core-card", title, width:3|6|9|12, hidden}`；默认布局；localStorage key `eh-dashboard-layout-v1`；校验/迁移/重置；导出/导入 JSON。
  - `layout-editor.tsx`：仪表盘「编辑布局」模式：
    - 显示/隐藏卡片；
    - 上下拖拽排序（HTML5 drag/drop 或 pointer events，不新增依赖）；
    - 宽度 1/2/3/4 列（3/6/9/12 栅格）；
    - 保存/取消/恢复默认；导出/导入 JSON。
  - 非编辑模式按保存顺序与宽度渲染。
- `src/pages/dashboard.tsx`：把「评分/建议/健康数据/最近记录/指标/波形/模块卡片」统一为可布局卡片；模块 widget 也参与布局；编辑模式不触发卡片 RPC 动画。
- 12 列网格；窄窗自动降为 12 列；`prefers-reduced-motion` 无拖拽动画。
- i18n `dashboard.layout.*` 中英。

### 3. 验证

- `npm run build`。
- CDP/Playwright：编辑模式开关、隐藏/恢复、拖拽排序、宽度变化、导出/导入 JSON、刷新后保持；亮/暗截图 `reports/screenshots/H2-*.png`；控制台 0 error。

## 文件所有权（只改这些）

- `schemas/module.schema.json`
- `src/features/modules/widgets/**`
- `src/features/layout/**`（新建）
- `src/pages/dashboard.tsx`
- `src/lib/i18n/**`（只新增 dashboard.layout 键）
- `docs/MODULE_CONTRACT_V2.md`
- `reports/H2-*.md`、`reports/screenshots/H2-*.png`

## 明确不做

- 不引入图表库/拖拽库；不做 iframe；不改模块安装/venv（H1）。
- 不改评分/教练/档案；不改 `api/__init__.py`。
- 不改 `prompts/`、`uploads/`；不 commit。

## 验收

报告 `reports/H2-layout-report.md`，≤80 行。

# 报告 · H2 布局编辑 + 声明式图表（bar/line/heatmap）

状态：完成

## 交付

- `schemas/module.schema.json`：`widgetView.type` 新增 `bar|line|heatmap` 与可选 `seriesPath`/`labelPath`；`valuePath` 改为按类型必填（bar/line 可用 seriesPath 替代，其余仍必填）。JSON Schema 自检通过，旧五种视图的列表继续通过校验。
- `src/features/modules/widgets/widget-view.tsx`：新增 SVG/CSS 柱状图、折线图、热力图（含 `[{date,value}]` 与二维数组）；颜色只走 `--eh-signal` / `--eh-chart-*` / `--eh-grid-line`；空数组、全 null、路径缺失统一显示「暂无数据」；未知类型仍降级；折线复用现有 600ms 绘制类。
- `src/features/modules/widgets/widget-card.tsx`：新增 `animate` 属性，编辑布局时关闭内容淡入；补充模块 i18n bundle 的副作用导入。
- `src/features/modules/widgets/use-widgets.ts`（新）：模块卡片查询 hook，暴露 `isSuccess` 以便布局安全合并；`widget-grid.tsx` 改为内部复用它（独立区块保留，仪表盘不再使用）。
- `src/features/layout/layout.ts`（新）：`LayoutItem{id,kind,title,width:3|6|9|12,hidden}`、默认布局、`eh-dashboard-layout-v1` 存储（`{version:1,items}`，兼容裸数组迁移）、严格校验/重复 id/上限 64、损坏数据回落默认、`mergeLayout` 清理已卸载模块并把新模块插到「最近记录」前、导出/导入 JSON、宽度→栅格类映射。
- `src/features/layout/layout-editor.tsx`（新）：`LayoutGrid` 编辑模式（显示/隐藏、HTML5 拖拽排序、上移/下移键盘替代、1/2/3/4 段宽度）与 `LayoutToolbar`（保存/取消/恢复默认/导出/导入 + 行内错误）；无新增依赖，无拖拽动画。
- `src/pages/dashboard.tsx`：评分、建议、健康数据、模块卡片、最近记录、指标、波形统一进一个 `.eh-grid`（12/8/1 列），按保存顺序与宽度渲染；编辑模式不触发卡片 RPC 淡入；布局在模块列表就绪后才清理/合并模块卡片，避免首帧误删已保存顺序。
- `src/lib/i18n/zh-CN.ts` / `en-US.ts`：新增 `dashboard.layout.*`（含错误码文案）。
- `docs/MODULE_CONTRACT_V2.md`：§2.2 字段表、三种图表的数据形状与示例；§8 兼容性说明。
- 截图：`reports/screenshots/H2-dashboard-light.png`、`H2-edit-light.png`、`H2-dashboard-dark.png`（1440 宽，整页）。

## 验证

- 命令：`npm run build` → pass（tsc + vite，`✓ built in 4.33s`，仅既有 >500 kB chunk 警告）。
- 命令：`backend\.venv\Scripts\python.exe -m pytest backend/tests/modules -q` → exit 0，328 passed（含并行 Agent 新增的 official 模块用例）。
- schema 校验（jsonschema 4.26，Draft 2020-12）：11 个用例全过——bar 用 valuePath/seriesPath、line、heatmap 对象/二维、stat 旧形状；拒绝 bar 无路径、heatmap/stat 缺 valuePath、未知 type、非法 labelPath；`check_schema` 自检通过。
- 布局库（Node 24 type-strip 直跑）：23 项全过——默认顺序/宽度、widget 合并与插入位置、卸载清理、保存读回、坏 JSON/未知版本回退、裸数组迁移、6 类非法条目、导入导出往返、重置清空、段↔宽度映射。
- CDP/headless Chrome 端到端（mock 数据 + Fetch 拦截 contributions/RPC）：24/24 pass——6 张模块卡片（bar 7 柱、line 8 点、heatmap 14 格、二维 12 格、stat 72.5、空图表「暂无数据」）；编辑开关、隐藏/恢复、宽度改为 6/12、合成拖拽后 waveform→首位、导入 JSON、非法导入报错、保存后 localStorage v1、刷新后顺序/宽度/隐藏保持、导出文件名与 JSON 内容、恢复默认、800px 单列、暗色渲染；控制台 error 0。
- 边界：无布局时用默认；坏数据/未知版本回落默认；重复 id、空布局、超限、非法 JSON 均有明确错误；模块列表未就绪时不清理已保存的模块卡片。

## 未做 / 偏离

- 截图脚本中 headless Chrome 会取消 blob 下载，导出改为拦截 `URL.createObjectURL` + 锚点 click，校验文件名与导出 JSON 内容；普通浏览器仍走原生下载。
- 默认宽度只能用 3/6/9/12：评分 9、建议 3、最近记录/指标各 6（原 8/4/7/5 不是合法值）。
- 引导卡片（导入/示例/格式）不在任务清单内，未纳入布局；统一布局区因此位于引导区之前，评分仍在首屏最前，引导区顺延到下方。
- 模块卡片区块标题被移除（卡片自身显示模块名）；模块查询失败时在布局下方保留一条错误+重试提示（mock 模式隐藏）。
- 热力图最多渲染 84 格并提示剩余数量；折线/柱状图的横轴标签最多抽样 6 个。
- `src/features/modules/types.ts` 不在所有权内，未改；`seriesPath`/`labelPath` 在 `widget-view.tsx` 用本地交点类型读取。
- 未新增图表专属 i18n key（`features/modules/i18n.ts` 不在所有权内），aria 复用 `moduleUi.widgets.sparklineAria` / `noData`。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `src/features/modules/types.ts`：建议把 `WidgetViewType` 扩为含 `bar|line|heatmap`，并在 `ModuleWidgetView` 增加 `seriesPath?`/`labelPath?`，避免前端各处再写本地类型。
- `src/features/modules/i18n.ts`：建议补 `widgets.chartAria`、热力图图例/空态文案；当前复用 sparkline 文案。
- 后端 `collect_contributions` 仍只做归属包装；图表形状依赖 manifest 的 schema 校验，若放宽需同步前端降级。

## 需要指挥官决策

- 引导卡片是否也要进入布局（目前按任务清单排除）。
- 布局是否要按成员分别保存（当前单一 key，符合本批提示词）。

## 建议下一批

- 布局编辑器增加键盘拖拽（上/下已有，可补宽度快捷键与焦点管理）。
- 图表补数据表视图/图例（UI 规范 §8 建议图表提供文字摘要与数据表）。

# 报告 · H7 模块适配包（候选 25–30）

状态：完成

## 交付

| 候选 | 目录 / id | 类型 | contributes | 依赖 |
|---|---|---|---|---|
| 25 stravalib | `modules/official/stravalib`<br>`io.github.stravalib.stravalib` | data-source | sources / importFormats / recordTypes | `stravalib>=2.0,<3` |
| 26 uPlot | `modules/official/uplot`<br>`io.github.leeoniya.uplot` | dashboard-widget | ui.widgets / ui.pages | `[]` |
| 27 ECharts | `modules/official/echarts`<br>`io.github.apache.echarts` | dashboard-widget | ui.widgets / ui.pages | `[]` |
| 28 Observable Plot | `modules/official/observable-plot`<br>`io.github.observablehq.plot` | dashboard-widget | ui.widgets / ui.pages | `[]` |
| 29 Tremor | `modules/official/tremor`<br>`io.github.tremorlabs.tremor` | dashboard-widget | ui.widgets / ui.pages | `[]` |
| 30 Activity Calendar | `modules/official/activity-calendar`<br>`io.github.grubersjoe.activity-calendar` | dashboard-widget | ui.widgets / ui.pages | `[]` |

- 每模块含 `module.json` / `README.md` / `LICENSE`(GPL-3.0-only 适配层) / `NOTICE` / `src/main.py` / `src/adapter.py`。
- Worker 均为 stdio JSON-RPC 2.0，支持 `initialize` / `warmup` / `health` / 业务方法 / `deactivate`；错误带 `INVALID_INPUT` 等可读 code。
- 业务方法：stravalib `activities.normalize|weekly`、`strava.fetch`；uplot `trend|summary`；echarts `chart.line|bar|distribution|summary`；plot `plot.trend|histogram|summary`；tremor `kpis|summary`；calendar `heatmap|summary`。
- 所有分析/展示输出带「非医疗器械，不用于诊断」。
- UI 模块不 vendor 上游 JS/React，按 122 要求用核心受控 `stat|sparkline|list|progress|text`；manifest `description` 注明「适配自 / inspired by」。

## 验证

- `backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_{stravalib,uplot,echarts,observable_plot,tremor,activity_calendar}.py`
  - 结果：**33 passed in 0.14s**。
  - 覆盖：manifest schema 校验（`schemas/module.schema.json`）、adapter 成功/空数据/非法输入、`handle()` 正常与错误路径。
- `backend\.venv\Scripts\python.exe -m ruff check <6 模块> <6 测试>`：**All checks passed!**
- 核心 manifest 解析：`load_manifest_file` + `check_compatibility` 六模块全部通过；`dependencies` 字段已被 schema 与 `Manifest` 支持（无需 pending）。
- stdio 烟测：uplot 与 stravalib 的 `initialize` / `health` / 业务方法 / 错误路径 / `deactivate` 均返回预期 JSON；中文路径下正常。
- stravalib 在核心 venv 未装上游库时 `health.dependencyAvailable=false`，`activities.*` 仍可离线工作。

## 未做 / 偏离

- UI 五模块按 122「不 vendor、用声明式 widget」执行；未使用 iframe，未引入 React/JS 运行时。
- H2 的 `bar` / `line` / `heatmap` 视图类型尚未落地：echarts/plot 输出 renderer-agnostic spec，页面暂用 `table`/`list`/`sparkline`；calendar 暂用 stat/list/table。
- 候选 25 stravalib 实为 Python data-source（候选表如此定义），按 data-source 构建；未当图表模块处理。
- `strava.fetch` 属联网路径，未在测试中实跑（无 token/网络）；缺依赖时返回 `DEPENDENCY_MISSING`。
- 上游 LICENSE 无法在当前离线环境重新抓取（curl/WebFetch 被拦）；`NOTICE` 已写仓库 URL、SPDX 并标注版权行待核，未复制上游代码，故未附上游 LICENSE 文件。
- 未生成 `checksums.json`（122 交付树未要求，打包时生成）。
- 测试文件名对含连字符 slug 使用下划线：`test_official_observable_plot.py`、`test_official_activity_calendar.py`。

## 跨区需求（需要别的 Agent 或指挥官处理）

- H2：补充 `bar` / `line` / `heatmap` 受控 view 后，可把 echarts、Observable Plot、Activity Calendar 的 spec 直接升级为原生视图。
- 核心数据桥：UI 模块只接收 RPC `params` 中传入的数据；若要让 widget 自动读取 `records`，需核心通用 widget 数据通道（当前契约 v2 §11 尚未实现）。
- 许可合规：联网后建议补抓上游 LICENSE 原文到 `LICENSES/` 并核对 NOTICE 中的版权行。

## 需要指挥官决策

- 「不 vendor 上游、仅在同能力原生 widget 的 NOTICE 中署名」是否作为 UI 类库模块的最终形态；若不接受，则这几个模块只能由核心内置。

## 建议下一批

- H2 落地后升级图表类型；若 data-source / importFormats 核心 glue 到位，再把 stravalib 接入导入页与周里程 widget。

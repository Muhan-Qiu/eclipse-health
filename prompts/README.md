# 提示词索引 · Stage G（30 模块 + 布局编辑）

> 指挥官文件。Stage F 已验收（`2c73a0a`，710 passed / 11 skipped）。
> 调研清单：`docs/MODULE_CANDIDATES_30.md`。用户决定：每模块 venv、30 个全做、核心声明式图表、完整拖拽布局。

## 阶段

| 编号 | 任务 | 提示词 | 报告 |
|---|---|---|---|
| H1 | 每模块独立 venv（前置） | `120-module-venv.md` | `reports/H1-module-venv-report.md` |
| H2 | 布局编辑器 + bar/line/heatmap | `121-layout-charts.md` | `reports/H2-layout-report.md` |
| H3–H7 | 5 × 6 个模块 | `122-module-pack.md` | `reports/H3..H7-modules-report.md` |

## 启动顺序

1. H1 先跑（schema/manifest/venv）。
2. H1 完成后并行：H2 + H3 + H4 + H5 + H6 + H7（6 个 low Agent）。

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/120-module-venv.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/H1-module-venv-report.md。
```

模块 Agent 用 `prompts/122-module-pack.md`，并在启动句里写清分配的候选编号（H3=1–6、H4=7–12、H5=13–18、H6=19–24、H7=25–30）。

## 文件所有权

- H1：`schemas/module.schema.json`、`modules/{manifest,package,manager}.py`、`tests/modules/**`、`MODULE_CONTRACT_V2`。
- H2：`schemas/module.schema.json`（H1 之后）、widgets、layout、dashboard、i18n。
- H3–H7：只写各自 `modules/official/<slug>/**` + `tests/modules/test_official_<slug>.py` + 报告。
- 模块 Agent 不改核心代码/UI/schema；H2 不改模块目录。

## 边界

- 30 个模块不预装，走官方索引按需安装。
- 依赖写 manifest，装进模块 venv；核心安装包不变大。
- 适配层包装，保留 LICENSE/NOTICE；双方共同作者。
- 图表用 SVG/CSS，不引入 ECharts/uPlot/iframe。
- 缺依赖的测试 skip，不污染核心 venv。

## 收尾

H1 + H2 + 5 份模块报告齐后：指挥官跑全量测试/ruff/build、打包 30 个 `.ehmod`、重建官方索引条目、重打安装包、更新 release notes。

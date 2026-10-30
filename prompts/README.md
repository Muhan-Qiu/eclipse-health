# 提示词索引 · B5 收口（3 个 Agent 并行）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> 当前批次：B5，目标把原始 44 项从 ~90% 收到 ~95%。
> B4 两波 8 个 Agent 已验收，报告在 `reports/B4-*.md`；提示词 `31`–`38` 仅作历史参考。

## 本轮（B5，3 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `50-a1-sample-d1-favorites.md` | A1 首次引导 + 真实示例记录；D1 收藏与筛选 | 中等 2/4 | high | `reports/B5-01-report.md` |
| `51-c7-engine-switch.md` | C7 通用引擎列表 + 选择 + 重新分析（当前仅 Cardia） | 困难 3/4 | high | `reports/B5-02-report.md` |
| `52-b4-07-finish.md` | B4-07 收尾：设置页通知开关 + 手动指标编辑 | 低 1/4 | medium | `reports/B5-03-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/50-a1-sample-d1-favorites.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/B5-01-report.md。
```

替换文件名/报告名即可。三个可同时开；本机 16GB，不要再加第 4 个编码 Agent。

## 文件所有权冲突预防

- `src/lib/api/**` 只归 B5-01；B5-02 用 `src/features/analysis/**` 本地 fetch，B5-03 用 `src/features/profile/api.ts`。
- `record-detail.tsx` / `analysis-panel.tsx` 只归 B5-02；B5-01 不改详情页。
- `src/lib/i18n/**` 三个都可能新增键：只允许**新增自己的键**，不得重写文件；发现冲突写进报告。
- `backend/api/__init__.py` 只归 B5-01（挂样本导入路由）；B5-02 的 engines 路由挂在现有 analyses router 内，不改 `__init__.py`。
- 不要同时跑 PyInstaller/Rust 构建与全量测试。

## 依赖与已知边界

1. **示例记录必须走真实导入管线**，不是 `VITE_USE_MOCK`；样本来自 `backend/resources/samples/`（MIT-BIH，随仓库）。
2. **C7 只有 Cardia 一个引擎**；不要造第二个引擎，框架要能接平台 #1 的 ONNX loader。
3. **通知开关是纯前端偏好**（localStorage），不进后端 settings、不调 Tauri invoke。
4. **收藏存 `records.data` JSON**，不做破坏性数据库迁移；筛选必须与分页一致。
5. H5 自动更新、G3 真机格式仍阻塞，不在本轮。

## 启动前检查

- 基线（2026-10-30 指挥官核查）：`ruff` 通过；`pytest backend/tests -q` 全绿；`npm run build` 通过。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 事实源：`docs/INTERNAL_API_V1.md`、`docs/V3_BUILD_PLAN.md` §27。

## 收尾

三份报告齐后，指挥官统一：全量 pytest/ruff/build、抽查截图、更新 `docs/DATA_SCHEMA_V1.md`（favorite）、更新 `V3_BUILD_PLAN.md` §22/§27、提交 checkpoint。

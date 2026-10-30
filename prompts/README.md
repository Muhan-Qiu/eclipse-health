# 提示词索引 · Stage C（集成修复 + 端到端验收 + 健康数据页）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> 当前批次：Stage C，3 个 Agent 并行。Stage B 已验收（`ad4c22e`）。
> 历史提示词 `31`–`38`、`50`–`52`、`60`–`64`、`70`–`74` 仅作参考。

## 本轮（Stage C，3 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `80-integration-fixes.md` | 契约补口 + 跨区修复 + 全量回归 | 困难 3/4 | high | `reports/C1-integration-report.md` |
| `81-e2e-acceptance.md` | 真实安装 → 卡片/工具/页面 → 卸载 | 中等 2/4 | medium | `reports/C2-e2e-report.md` |
| `82-health-data-page.md` | 健康数据页（Apple/小米记录可见） | 中等 2/4 | high | `reports/C3-health-data-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/80-integration-fixes.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/C1-integration-report.md。
```

```
阅读 prompts/00-COMMON.md 和 prompts/81-e2e-acceptance.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/C2-e2e-report.md。
```

```
阅读 prompts/00-COMMON.md 和 prompts/82-health-data-page.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/C3-health-data-report.md。
```

三个可同时开；本机 16GB，不要再加第 4 个 Agent。

## 文件所有权冲突预防

- `schemas/**`、`llm/agent.py`、`llm/providers.py`、`app.py`、`ui/progress.tsx`、modules 的 query invalidation 只归 C1。
- `scripts/e2e_stage_c.py`、`fixtures/modules/e2e/**`、C2 报告/截图只归 C2；C2 **不改生产代码**。
- `api/records.py`、`health-data.tsx`、`App.tsx`、`nav.ts`、`lib/api/*`、`lib/i18n/*` 只归 C3。
- C1 不碰 records 页面；C3 不碰模块渲染器；C2 只写测试/报告。

## 已知边界

1. C1 的 schema 只补 `link` 与 `format`，不改已发布的字段语义。
2. C2 用测试模块，不提交 `.ehmod`；发现问题只写报告，不修生产代码。
3. C3 只做列表/筛选/展开，不做图表、睡眠会话合并。
4. 华为/Zepp/Samsung 仍等用户样本；H5/G3 仍阻塞。
5. 本轮完成后由指挥官重打 NSIS 候选包，交用户试用并收集动画/功能意见。

## 启动前检查

- 基线（2026-10-30）：ruff 通过；`pytest backend/tests` 568 passed / 11 skipped；`npm run build` 通过。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 事实源：`docs/MODULE_CONTRACT_V2.md`、`docs/V3_BUILD_PLAN.md` §30。

## 收尾

三份报告齐后，指挥官统一验收、提交 checkpoint、重打 NSIS 候选包，交用户安装试用；之后进入 Stage D（动画/视觉 + 反馈修复 + 最终包）。

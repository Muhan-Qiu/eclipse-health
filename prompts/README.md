# 提示词索引 · Stage B（平台展示/工具 + 多源导入实现 + LLM 联调）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> 当前批次：Stage B，5 个 Agent 并行。Stage A 已验收（`1a5b33e`）。
> 历史提示词 `31`–`38`、`50`–`52`、`60`–`64` 仅作参考。

## 本轮（Stage B，5 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `70-widget-renderer.md` | 平台 #2：首页 widget 渲染器 | 困难 3/4 | high | `reports/B1-widgets-report.md` |
| `71-module-tools.md` | 平台 #3：模块工具注册表 → 助手 | 困难 3/4 | high | `reports/B2-module-tools-report.md` |
| `72-module-pages.md` | 平台 #4 UI：模块页渲染器 | 困难 3/4 | high | `reports/B3-module-pages-report.md` |
| `73-health-import-impl.md` | S2：Apple + 小米直接导入 | 困难 3/4 | high | `reports/B4-health-import-report.md` |
| `74-llm-live.md` | LLM 真实 provider 联调（DeepSeek/OpenCode） | 中等 2/4 | medium | `reports/B5-llm-live-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/70-widget-renderer.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/B1-widgets-report.md。
```

替换文件名/报告名即可。五个可同时开；本机 16GB，不要再加第 6 个 Agent。

## 文件所有权冲突预防

- `src/features/modules/api.ts`、`types.ts`、`i18n.ts`、`dashboard.tsx` 只归 B1。
- `src/features/modules/module-detail.tsx`、`src/App.tsx`、`src/pages/module-page.tsx`、`features/modules/pages/**` 只归 B3；B3 不碰 B1 的 api/types/i18n。
- `llm/tools.py`、`llm/agent.py`、`assistant/tool-trace.tsx` 只归 B2；`llm/providers.py`、`assistant/provider-card.tsx`、`assistant/i18n.ts` 只归 B5。
- `backend/importers/**`、`components/import/**`、共享 i18n 的 import 段只归 B4。
- 不要同时跑 PyInstaller/Rust 构建与全量测试；本轮不重打安装包。

## 已知边界

1. 模块 widget/page 只支持 `MODULE_CONTRACT_V2.md` 的受控组件；未知类型降级，不执行任意代码。
2. 模块工具必须已授予 `llm` 权限；结果裁剪，不返回波形/备注/成员姓名。
3. S2 只做 Apple + 小米；华为/Zepp/Samsung 等用户样本；不做 Health Connect/AES 解密。
4. LLM 联调不得读取/打印 CC Switch 数据库；用环境变量（`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH` 或 `EH_TEST_*`），缺凭据就 skip。
5. H5 自动更新、G3 真机格式仍阻塞。

## 启动前检查

- 基线（2026-10-30）：ruff 通过；`pytest backend/tests` 547 passed / 3 skipped；`npm run build` 通过。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 事实源：`docs/MODULE_CONTRACT_V2.md`、`docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`、`docs/V3_BUILD_PLAN.md` §29。

## 收尾

五份报告齐后，指挥官统一验收、更新计划、提交 checkpoint；随后写 Stage C：集成/端到端验收、发布打包（NSIS）、用户看包、动画收尾。

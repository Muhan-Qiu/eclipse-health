# 提示词索引 · Stage A（平台底座 + 多源导入研究 + 发布准备）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> 当前批次：Stage A，5 个 Agent 并行（3 编码 + 1 研究 + 1 发布准备）。
> B4/B5 已完成，报告见 `reports/`；历史提示词 `31`–`38`、`50`–`52` 仅作参考。

## 本轮（Stage A，5 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `60-platform-v2-contract.md` | 平台 v2 契约 + 贡献注册表 + loader 骨架 | 困难 3/4 | high | `reports/A1-platform-contract-report.md` |
| `61-module-data-api.md` | 模块数据 API `records.*` + 隔离/权限/审计 | 困难 3/4 | high | `reports/A2-module-data-report.md` |
| `62-onnx-engine-loader.md` | 平台 #1：通用 ONNX 分析引擎 loader | 困难 3/4 | high | `reports/A3-onnx-engine-report.md` |
| `63-health-import-research.md` | S1 多源健康数据直接导入研究（只写文档） | 中等 2/4 | medium | `reports/A4-health-import-research-report.md` |
| `64-release-prep.md` | 路由懒加载 + README + 依赖声明 + release notes | 低 1/4 | medium | `reports/A5-release-prep-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/60-platform-v2-contract.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/A1-platform-contract-report.md。
```

替换文件名/报告名即可。五个可同时开；本机 16GB，不要再加第 6 个 Agent。

## 文件所有权冲突预防

- `schemas/module.schema.json`、`modules/contributions.py`、`modules/api.py` 只归 A1。
- `modules/manager.py`、`permissions.py`、`audit.py` 只归 A2；A2 不改 `api.py`/`contributions.py`。
- `analysis_service/**` 只归 A3；A3 不改 `modules/**`、`schemas/**`。
- `src/App.tsx`、`README.md`、`backend/pyproject.toml`、`docs/RELEASE_NOTES_DRAFT.md` 只归 A5。
- 测试 fixture 已按 `fixtures/modules/{contributions,host,onnx}/` 分目录，不要写对方目录。
- 不要同时跑 PyInstaller/Rust 构建与全量测试；本轮 A5 **不重打安装包**。

## 已知边界

1. **不伪造第二引擎**：A3 只做通用 loader；生产环境第二引擎必须来自已安装模块。
2. **模块数据可见性**：A2 按「自己创建的记录 + 自己声明 recordType 的记录」实现，越权按 NOT_FOUND。
3. **S1 只出结论**：A4 不写解析器；S2 由下一轮按研究结论实现。
4. **发布包**：A5 只做懒加载/README/依赖/notes，不跑 Tauri/PyInstaller 构建。
5. H5 自动更新、G3 真机格式仍阻塞，不在本轮。

## 启动前检查

- 基线（2026-10-30）：ruff 通过；`pytest backend/tests` 487 passed / 3 skipped；`npm run build` 通过。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 事实源：`docs/V3_BUILD_PLAN.md` §27/§28、`docs/MODULE_CONTRACT_V1.md`、`docs/INTERNAL_API_V1.md`。

## 收尾

五份报告齐后，指挥官统一：全量 pytest/ruff/build、抽查、更新计划、提交 checkpoint；然后写 Stage B 提示词（widget 渲染器 / 工具注册表 / 模块页渲染器 / S2 导入实现）。

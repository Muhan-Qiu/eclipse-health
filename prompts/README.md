# 提示词索引 · Stage D（动画基线 + 视觉 QA）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> 当前批次：Stage D，2 个 Agent 并行。Stage C 已验收（`130de66`），候选安装包正在构建。
> 历史提示词 `31`–`38`、`50`–`52`、`60`–`64`、`70`–`74`、`80`–`82` 仅作参考。

## 本轮（Stage D，2 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `90-motion-baseline.md` | 动画系统基线（启动/切页/卡片/波形） | 中等 2/4 | high | `reports/D1-motion-report.md` |
| `91-visual-qa.md` | 视觉/可用性 QA（亮暗/对比/间距/窄窗） | 中等 2/4 | high | `reports/D2-visual-audit.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/90-motion-baseline.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/D1-motion-report.md。
```

```
阅读 prompts/00-COMMON.md 和 prompts/91-visual-qa.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/D2-visual-audit.md。
```

两个可同时开；本机 16GB，不要再加第 3 个 Agent（安装包构建也在跑）。

## 文件所有权冲突预防

- D1：`src/index.css`、`src/branding/**`、`src/components/layout/**`、`src/components/common/**`、`src/lib/motion.ts`、`dashboard.tsx`、`record-detail.tsx`、`waveform-viewer.tsx`。
- D2：其余页面、`src/components/ui/**`、`src/features/**`（widgets/pages 除外）、`src/lib/i18n/**`。
- D2 发现 D1 文件的问题只记录，不修。
- 不要同时跑 `tauri build`/PyInstaller 与全量测试；安装包由指挥官统一打。

## 反馈闭环

- 用户安装候选包后的具体意见进 **D3**（等反馈后由指挥官写提示词）：功能修复 + 动画/视觉细节。
- 本轮 D1/D2 只做通用基线，不猜测用户偏好。

## 启动前检查

- 基线（2026-10-31）：ruff 通过；`pytest backend/tests` 594 passed / 11 skipped；`npm run build` 通过。
- 候选安装包：`src-tauri/target/release/bundle/nsis/eclipse health_0.1.0_x64-setup.exe`（Stage C 重打）。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。

## 收尾

D1/D2 报告齐 + 用户反馈到位后：指挥官统一验收、合并 D3 修复、重打最终包、更新 release notes/校验和。

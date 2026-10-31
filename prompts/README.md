# 提示词索引 · D3 最终打磨（最后一轮代码）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`。
> 当前批次：D3，1 个 Agent。D1/D2 已验收（`30768de`）。
> D3 完成后：指挥官重打最终 NSIS 包、填 release notes/校验和，交用户验收。

## 本轮

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `92-final-polish.md` | 波形 R 峰反馈 + 模块卡加载态 + 时长格式 + 仪表盘空白 + 报告摘要 + 列表入场 + 用户反馈 | 中等 2/4 | high | `reports/D3-final-polish-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/92-final-polish.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/D3-final-polish-report.md。
```

## 用户反馈

- 用户已确认动画方向与三条具体动画要求，D1 已实现；D3 只补 D1 报告中的波形/模块卡缺口。
- 用户安装候选包后的新增意见，由指挥官填入提示词 §7 后再执行；如果暂时没有，就按 1–6 执行。

## 已知边界

- 不改后端/数据/接口；不改 D1 的启动/logo/导航转场。
- 时长格式统一为 `M:SS` / `H:MM:SS`，默认不显示毫秒。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 收尾

D3 报告到后：指挥官跑全量 `pytest` + `ruff` + `npm run build`，重打 NSIS 最终包，更新 `docs/RELEASE_NOTES_DRAFT.md` 的校验和/大小，提交最终 checkpoint。

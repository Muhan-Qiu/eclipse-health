# 提示词索引 · Stage F（健康评分 / 教练 / 记忆 / OHS）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`。
> 当前批次：Stage F，5 个 Agent 并行，**全部 low 思考强度**。Stage E 已验收（`6276eed`）。
> 用户第三轮需求见 `docs/USER_FEEDBACK.md`。

## 本轮（Stage F，5 个并行，low）

| 提示词 | 任务 | 报告 |
|---|---|---|
| `110-home-scores-ui.md` | 首页「概览」重组 + 评分/建议 UI + 首启 LLM Key 引导 | `reports/G1-home-scores-report.md` |
| `111-scoring-backend.md` | 规则评分 + 建议后端 | `reports/G2-scoring-report.md` |
| `112-profile-exercise-memory.md` | 档案新字段 + 运动记录 + 个性化记忆 | `reports/G3-profile-exercise-memory-report.md` |
| `113-coach-memory.md` | 教练 + Open-Meteo + 记忆注入 + 助手预设 | `reports/G4-coach-report.md` |
| `114-ohs-connector.md` | 可选 Open Health Sync 连接器 | `reports/G5-ohs-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/110-home-scores-ui.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/G1-home-scores-report.md。
```

其余四份同理替换文件名/报告名。

## 文件所有权冲突预防

- G1：dashboard/health-data/nav/App/onboarding/scores UI/api 客户端/i18n。
- G2：`backend/.../scoring/**`、`tests/scoring/**`、`docs/SCORING.md`。
- G3：profile 后端 + exercises/memory + `src/features/profile/**`。
- G4：`backend/.../coach/**`、`llm/agent.py`、`src/features/assistant/**`、assistant 页。
- G5：`backend/.../ohs/**`、`tests/ohs/**`、settings.tsx、OHS 文档。
- **G2–G5 都不要改 `api/__init__.py`**；各自建 router，指挥官统一挂载。
- i18n 多方新增：只新增自己的键，不重写文件。
- 不要同时跑 `tauri build`/PyInstaller；本轮结束后统一打包。

## 已知边界

1. 评分只用公开区间规则，非诊断；缺项不显示。
2. 首启提示 LLM Provider Key，不是外部访问 Key。
3. 教练天气 Open-Meteo，失败不影响回答。
4. 记忆只存本机、可关闭注入；健康档案页编辑。
5. OHS 可选；普通用户不需要 Docker，内置 Apple/小米导入继续可用。
6. OHS token 用 DPAPI 加密；不复制 OHS 代码。

## 收尾

五份报告齐后：指挥官挂载 routers、跑全量测试/ruff/build、处理冲突、重打 NSIS、更新 release notes/校验和。

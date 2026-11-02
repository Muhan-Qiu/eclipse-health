# 00 · 所有 Agent 共用规则

> 你是 eclipse health v3 的施工 Agent。本文件是硬约束；与你的任务提示词冲突时，以任务提示词为准。
> 项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 1. 先读什么（按顺序）

1. 根目录 `CLAUDE.md`：项目角色与已确认决策。
2. `docs/V3_BUILD_PLAN.md`：总控计划、批次、所有权矩阵、验收门。
3. 你自己的任务提示词 `prompts/0X-*.md`。
4. 任务提示词里点名的 docs。**不要**全量浏览 `docs/`、`node_modules/`、`backend/.venv/`。

## 2. 项目事实

- 桌面端：Tauri 2 + React 19 + TypeScript + Vite 8 + Tailwind 4 + shadcn/ui（Nova/Radix）。
- 后端：Python 3.12 + FastAPI + SQLModel + Pydantic v2，位于 `backend/`，包名 `eclipse_health_backend`。
- 模型：`backend/resources/models/cardia/`（ONNX + TorchScript + `preprocess.json`）。
- 样本：`backend/resources/samples/`（MIT-BIH 100/200/208）。
- 上一版代码可参考：`..\v1\`（`feature_extract.py` / `ecg_tools.py` / `cardia_classifier.py`）与 `..\V2\发布预权重与评分信息\推理代码\`（`inference.py` / `feature_extract.py`）。**只读，不复制仓库结构。**
- 仓库已初始化（私有本地仓库，无 remote，baseline `12f4dae`）。**不要 commit / push / 改历史**；只读的 `git status` / `git diff` 可以用于自查。

## 3. 工具链（重要）

`uv` 不在 PATH，不要用 `uv run`。直接用后端虚拟环境：

```powershell
# 在项目根目录
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
```

```powershell
npm run build
npm run dev        # Vite，1420
```

- 依赖已装齐；**不要**新增全局依赖、不要改系统环境、不要 `npm install`/`pip install`，除非任务提示词明确允许。缺依赖就写进报告。
- `npm run build` 基线已通过（2026-10-30 指挥官核查）；不要动 `tsconfig.json`，若构建失败先确认不是自己引入的。
- 需要联网查资料时：不要用 WebSearch（本机上游不支持），用 WebFetch 打开 Bing / DuckDuckGo 结果页。优先不联网。
- **例外**：B4-02（数据采集）、B4-03（设备适配）、B4-08（LLM 联调）允许按各自提示词下载公开数据/公开模型/公开样本；必须记录来源 URL、许可证、sha256，下载物放 `uploads/` 或临时目录，不得提交受限数据集。其他 Agent 仍默认不联网。

## 4. 范围纪律

- **只改任务提示词「文件所有权」列出的路径。** 其他文件只读。
- 本轮三个 Agent 并行工作，别人文件随时在变。看到别人区域的报错、TODO、半成品，不要修、不要格式化、不要删除；写进你的报告「跨区需求」。
- 不修改 `CLAUDE.md`、`docs/`、`prompts/`、`uploads/`。`uploads/` 里的用户样本只读，绝不写入、绝不外传。
- 不创建与任务无关的目录、文档、示例、README。交付要能跑、能测、能被下一个人接手。
- 不做「顺手重构」；不引入新框架；不换现有 UI 组件库。
- 禁止破坏性命令（删除目录、`git reset`、清空数据库、改注册表）。测试数据只用临时目录。
- 不要声称完成未验证的事。测试失败就如实写。

## 5. 代码要求

- Python：类型标注、`ruff` 通过、pytest 覆盖主路径与边界。业务错误用明确的异常/HTTP 状态码。
- TS/React：`tsc` 通过；组件函数式；状态最小化；不写 `any` 逃逸；样式走设计令牌，不写死颜色。
- 标识符用英文；用户可见文案用 i18n key（默认 `zh-CN`，备 `en-US`）。
- 注释只写「为什么」，不写「是什么」；中文注释可以。
- 隐私：不记录波形内容到日志；不保存原始文件名（只存哈希）；不发遥测；不把任何健康数据发到网络。

## 6. 验收与自检

跑任务提示词里的验收命令，把**真实输出**（通过数量、失败信息、耗时）写进报告。至少覆盖：

- 正常路径；
- 一个边界/非法输入；
- 一个空数据/首次运行场景。

UI 任务额外要求：`npm run build` 通过；亮色/暗色各一张截图，放 `reports/screenshots/`；控制台无 error。

## 7. 报告（必须写）

完成后写 `reports/<你的编号>-report.md`，≤80 行，中文，固定结构：

```markdown
# 报告 · B1-0X <任务名>
状态：完成 / 部分完成 / 阻塞

## 交付
- 文件/功能：一句话
## 验证
- 命令：`...`
- 结果：pass/fail、数量、耗时
## 未做 / 偏离
- ...
## 跨区需求（需要别的 Agent 或指挥官处理）
- ...
## 需要指挥官决策
- ...
## 建议下一批
- ...
```

不要粘贴大段代码或完整日志；报告是给指挥官省上下文的。

## 8. 什么时候停

出现以下情况，立即停止扩展，写报告并结束，不要硬撑：

- 关键接口与文档矛盾，且无法在不改别人文件的前提下解决；
- 缺依赖、缺样本、缺权限，导致主路径无法验证；
- 同一错误连续排查 3 轮仍无进展；
- 发现任务范围明显超出本批（记录到「建议下一批」，不要开做）。

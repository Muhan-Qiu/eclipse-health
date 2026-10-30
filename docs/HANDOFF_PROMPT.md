# 交接提示词 · eclipse health v3 核心负责人

> 2026-10-30 · 给下一任总指挥官/核心负责人
> 用法：把本文件全文粘到新会话第一条消息；然后按「第一步」执行。
> 原则：**不要从零重新规划**；先读现有文档和报告，再问用户 3 个未决问题。

---

## 0. 你的角色

你是 eclipse health v3 的**总指挥官**，不是实现者：

- 不写业务代码；负责拆任务、写 Agent 提示词、定文件所有权、按批验收、更新计划。
- 用户会自己开 Agent 跑任务；提示词放 `prompts/`，Agent 报告放 `reports/`，外部文件放 `uploads/`。
- 审查按批做：先读报告 + 跑测试/构建 + 抽查关键文件/截图，不逐行读代码。
- 上下文要省：不要全量浏览仓库；只读本文列出的文档和最新报告。

项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

---

## 1. 项目一句话

eclipse health v3：Windows 桌面端本地优先健康应用，Tauri 2 + React 19 + TypeScript + Python FastAPI sidecar + SQLite；核心能力是 ECG 导入/分析（Cardia 2.0 ONNX）、记录/趋势/对比、PDF/PNG 报告、LLM 助手、模块化生态。

已确认的产品原则见根目录 `CLAUDE.md`：开源、本地优先、模块化、官方与第三方同一套接口、UI 受设计令牌约束。

---

## 2. 先读这些（按顺序，别多读）

1. `CLAUDE.md`
2. `docs/V3_BUILD_PLAN.md`：总控计划、B1–B4 验收、进度、平台排期、**§24 三星健康方向纠正**
3. `prompts/README.md`：当前批次与启动方式
4. `reports/` 下最新的 `B4-*.md`（先看状态行和「未做/跨区」）
5. `docs/MODULE_DEVELOPER_GUIDE_V1.md`：第三方模块能接什么、不能接什么
6. 需要时再看：`docs/INTERNAL_API_V1.md`、`docs/DATA_SCHEMA_V1.md`、`docs/UI_COMPONENT_SPEC_V1.md`、`docs/MODULE_CONTRACT_V1.md`

---

## 3. 当前状态（2026-10-30，需用 `reports/` 复核）

### 已完成

- B1 地基：后端核心/数据层、模块内核、Cardia 分析库、UI 外壳。
- B2 端到端：导入 → 分析 → 记录详情 → 持久化；桌面壳/托盘/启动动画/logo。
- B3：趋势、两条记录对比、PDF/PNG 报告、LLM 助手（mock 验证）、ONNX 启动 150s→1.2s。
- B4：
  - B4-01 打包：**完成**，NSIS 安装包已产出。
  - B4-02 样本：**部分完成**，EDF/SCP-ECG 有真实公开样本；Apple/Samsung/华为无公开原始导出。
  - B4-03 格式适配器：EDF/SCP-ECG 已验证；三家厂商 `experimental`。
  - B4-04 导出/备份/隐私/诊断/设置：完成。
  - B4-05 波形增强：完成（心搏列表/节律条/12 导联展示/PNG/快捷键）。
  - B4-06 模块安装/权限/审计 UI：完成。
  - B4-07 档案/手动指标/通知：代码已接线，**报告未到**，需最终验收。
  - B4-08 LLM 真实联调：**未开始**；助手仍是 mock，真实 provider 需要 Ollama/API Key。

### 原始 44 项确认功能

- 约 **88–90%** 完成；39 项完成/基本完成，4 项部分完成，1 项阻塞。
- 剩余：A1 真实示例记录、C7 切换引擎、D1 收藏、H5 自动更新（缺签名/服务器）、G3 真机格式（缺样本）。
- 详细矩阵见 `docs/V3_BUILD_PLAN.md` §18/§22。

### 安装包

- `src-tauri/target/release/bundle/nsis/eclipse health_0.1.0_x64-setup.exe`（约 211.5MB）
- sidecar onedir 约 594MB；未做代码签名/自动更新；SmartScreen 可能提示未知发布者。

---

## 4. 关键环境事实

- `uv` **不在 PATH**；后端命令用：
  `backend\.venv\Scripts\python.exe -m ...`
- venv **没有 pip**；不要新增 Python 依赖。已装：numpy/scipy/wfdb/neurokit2/onnxruntime/matplotlib/Pillow/Jinja2/litellm/pydantic-ai/sse-starlette。
- 16GB 内存；B3 四路并行出现过 OOM。建议最多 4 个重编码 Agent，或 6 个（其中 2 个研究/文档）。
- 不要同时跑 Rust/PyInstaller 构建和大量测试。
- Git 是**私有本地仓库，无 remote**；不要 push。提交前检查 `.gitignore`（`uploads/`、`.venv`、`node_modules`、`backend/.data`、`src-tauri/binaries/`、`src-tauri/_internal/`、打包 dist 均已忽略）。
- 本机 WebSearch 不可用；联网用 WebFetch + Bing/DuckDuckGo，或 `curl.exe`。

---

## 5. 模块生态现状（重要，别再误解）

- **能装、能启停、能授权、能审计、能通过 `/api/v1/modules/{id}/rpc` 调用**：已完成。
- **自动接进主界面/导入/分析/报告/LLM 工具**：除内置 Cardia 外，尚未接线。
  - 分析：`analysis_service/bridge.py` 写死 Cardia 模块 ID/引擎/方法；无通用引擎注册。
  - 导入：`importers/registry.py` 只注册内置适配器。
  - 报告/LLM 工具/UI：无 contribution loader/渲染器。
- 第三方模块作者现在可走「纯 RPC 模块」；完整指南：`docs/MODULE_DEVELOPER_GUIDE_V1.md`，Agent 模板：`prompts/40-module-author-template.md`。
- 12 导联只做展示；Cardia 2.0 是单导联模型。

---

## 6. 用户最新需求与一处已纠正的误解

### 6.1 三星健康方向（重要，别再写反）

用户原意：

> 酷安上有工具可以把各种健康数据**导入到三星健康**（部分付费）。既然手机 APP 都有，网页端应该有办法。加进计划，指派 Agent 搜索实现方法并实现，让用户跟着我们的操作把导入的数据给我们；用户可以使用第三方现有 APP，我们不必自己设计。

**方向是「导入到三星健康」，不是「从三星健康导出」。** 上一任负责人曾写成导出，已在 `docs/V3_BUILD_PLAN.md` §24 纠正。

新负责人必须先让用户在三种目标里选一个，再实现：

- **A. 网页端工具，把数据写入三星健康**（若三星有公开写入 API/网页入口且 ToS 允许）。
- **B. 只做操作指南**：用户用现有第三方 App 导入三星健康，再按我们给的步骤把数据交给我们。
- **C. 绕过三星健康**：我们直接解析用户手头的源数据（Apple/华为/小米导出），三星健康只作为用户侧汇聚工具。

合规：只用官方公开能力或用户自有数据；不逆向私有 API、不破解、不代下载、不绕过付费工具。

### 6.2 其他新增计划

- 第三方平台 #1–#4：ONNX 推理、首页显示卡片、工具型 Agent、带自有数据的领域 Agent。
- 发布/上线 Agent：重打安装包、release notes、校验和、冒烟；自动更新/签名仍缺私钥/服务器/证书。
- 用户安装看包后给动画建议，再开最后一轮动画/视觉优化。

详细排期见 `docs/V3_BUILD_PLAN.md` §23/§24/§25/§26。

---

## 7. 当前排期（供决策，不要直接开跑）

- 原计划 100 → 做 #1–#4 约 130–135。
- 平台 #1–#4：3 轮 × 4 Agent，约 2–3 周；最快 4 轮（6–8 路并行），约 2 周，因为「用户看包给动画意见」是串行。
- 三星导入：S1 研究 + S2 实现，待 A/B/C 确认。
- 发布 + 动画：最后两轮。

**下一步不要直接写代码或一次性开 8 个 Agent。** 先做下面「第一步」。

---

## 8. 第一步（新负责人照做）

1. `git status`、`git log --oneline -5`，确认工作区是否有未提交改动。
2. 看 `reports/` 最新 B4 报告：B4-07 是否已交、B4-08 是否开始。
3. 跑一次基线（时间允许）：
   - `backend\.venv\Scripts\python.exe -m ruff check backend modules/official scripts`
   - `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`
   - `npm run build`
4. 向用户确认 3 件事（不要替用户决定）：
   - **三星导入目标是 A / B / C 哪一个？**
   - **示例领域 Agent 做「体重/血压」还是「饮食/能量」？**
   - **先收口原始 44 项（A1/C7/D1/QA），还是直接开平台 #1–#4？**
5. 根据回答更新 `docs/V3_BUILD_PLAN.md`，再写下一轮提示词到 `prompts/`。
6. 每个 Agent 提示词必须包含：必读文档、任务范围、文件所有权、明确不做、验收命令、报告路径；并行任务文件不重叠。

---

## 9. 审查与验收口径

- 每个 Agent 报告 ≤80 行，写状态/交付/验证/未做/跨区需求。
- 指挥官验收：读 4 份报告 → 跑全量测试/ruff/build → 抽查 4 个关键点/截图 → 更新计划 → 提交 Git checkpoint（用户允许时）。
- 不追求临床级安全/上线级运维；这是个人向本地应用。但不要伪造测试结果、不要声称未验证的功能已完成。
- 做不到的事要直说：H5 自动更新、G3 真机格式、三星官方网页写入能力，都可能受外部条件阻塞。

---

## 10. 文件地图

```
docs/V3_BUILD_PLAN.md              # 总控计划（先读 §17–§26）
docs/MODULE_DEVELOPER_GUIDE_V1.md  # 第三方模块能力/限制/接入方法
docs/INTERNAL_API_V1.md            # 内部 REST 契约
docs/DATA_SCHEMA_V1.md             # 数据 Schema
docs/UI_COMPONENT_SPEC_V1.md       # UI/令牌规范
docs/MODULE_CONTRACT_V1.md         # 模块契约
prompts/                           # Agent 提示词；README 是索引
reports/                           # Agent 报告；B1–B4 历史
uploads/                           # 用户外部样本/模型（gitignored）
backend/                           # FastAPI + 分析 + 模块内核
src/                               # React UI
src-tauri/                         # Tauri 桌面壳/打包
modules/                           # 官方模块（cardia）+ demo.echo 模板
schemas/module.schema.json         # manifest 事实源
scripts/                           # 打包/构建脚本
```

---

## 11. 交接时的工作区状态

- 分支 `main`，私有本地仓库，无 remote。
- 最近提交：`49eb968`（三星导入/发布/动画计划）、`7f2ef9f`（B4 进度评估）、`f8c71da`（模块指南）、`920ae0b`（B4 模块指南/校验）、`f3201eb`（B3）。
- 可能有未提交的 B4-07/08 相关改动；先 `git status` 确认，不要盲目 `git add -A`。

---

**给新负责人的一句话：先读 `docs/V3_BUILD_PLAN.md` 的 §17–§26，再问用户 A/B/C 和优先级。不要重新发明计划，也不要把三星健康的方向再写反。**

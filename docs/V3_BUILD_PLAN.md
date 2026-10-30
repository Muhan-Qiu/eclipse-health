# eclipse health v3 · 总控计划

> 更新：2026-10-29 · 指挥官文件 · B2 完成 / B3 准备中
> 本文件只记录「谁在什么时候做什么、边界在哪、怎么验收」。细节看各 Agent 提示词。

## 0. 指挥官工作方式

- 指挥官不写业务代码，只做：拆任务、写提示词、定边界、按批验收、记录决策。
- 每批同时 3～4 个 Agent；每个 Agent 的提示词在 `prompts/`，完成后报告写 `reports/`。
- 审查按批进行，不逐行审代码：先看报告 + 测试/构建结果，再抽查关键文件与截图。
- 用户提供的样本、模型、导出包统一放 `uploads/`（已 gitignore，不入库、不外传）；Agent 只读不写。

## 1. 当前状态（已核实）

| 项 | 状态 |
|---|---|
| 前端 | Tauri 2 + React 19 + TS + Vite 8 + Tailwind 4 + shadcn/ui（25 组件）已装好；仍是脚手架页面 |
| 后端 | `backend/` 有 uv 工程与 `.venv`，`eclipse_health_backend` 只有空 `__init__.py` |
| 模型 | Cardia 2.0 ONNX 5.4MB + TorchScript 3.5MB；`preprocess.json` / `model_config.json` 齐全 |
| 样本 | MIT-BIH `100/200/208`（`.hea/.dat/.atr`）在 `backend/resources/samples/` |
| 文档 | 生态、模块契约、注册表、UI 规范、数据 Schema、功能清单、IDEAS 均已成稿（v1 草案） |
| 工具链 | `uv` 不在 PATH；用 `backend\.venv\Scripts\python.exe -m ...` 直接运行 |
| 基线 | `npm run build` 当前失败：TS5101（`baseUrl` 在 TS 6 弃用），由 B1-UI 修复 |
| 版本控制 | 已初始化**私有本地仓库**（无 remote），baseline `12f4dae`；`uploads/`、`.venv`、`node_modules`、`.data`、本地 Claude 配置等已忽略 |

## 2. 路线图

| 批次 | 目标 | 内容 |
|---|---|---|
| **B1 地基** | 四条腿站稳 | 后端核心/数据层、模块系统内核、Cardia 分析引擎、UI 外壳与设计系统 |
| **B2 贯通** | 第一条端到端链路 | Cardia 包成 `analysis-model` 模块、Samsung 适配（需样本）、桌面壳（托盘/单实例/窗口记忆）、品牌启动动画与 logo、导入→分析→展示 |
| **B3 功能** | 44 项已确认功能的主体 | 记录库/趋势/报告/LLM 解释/命令面板/对比/导出等 |
| **B4 生态** | 开放与分发 | Apple/华为/SCP-ECG 模块、模型管理器、注册表与自动扫描、REST/MCP、自动更新 |

> 原则：模块系统必须先于业务功能稳定；B1 不碰用户功能，只打地基。

## 3. B1 任务表

| 编号 | 任务 | 难度 | 建议思考强度 | 主要产出 | 文件所有权 |
|---|---|---|---|---|---|
| B1-01 | 后端核心与数据层 | 困难 3/4 | **high** | FastAPI 应用、SQLite/SQLModel、成员/记录/信号 API、文件存储、测试 | `backend/src/eclipse_health_backend/{app,settings}.py`、`db/`、`domain/`、`api/`、`storage/`、`backend/tests/{core,api}`、`backend/pyproject.toml` |
| B1-02 | 模块系统内核 | 极难 4/4 | **max** | manifest Schema、`.ehmod` 安装、权限、审计、stdio JSON-RPC 宿主、示例 echo 模块 | `backend/src/eclipse_health_backend/{modules,audit}/`、`schemas/`、`modules/`、`backend/tests/modules` |
| B1-03 | Cardia 分析引擎 | 困难 3/4 | **high** | 特征提取 + ONNX 推理 + 质量/心搏/测量管线、CLI、与 V2 推理对齐测试 | `backend/src/eclipse_health_backend/analysis/`、`backend/tests/analysis` |
| B1-04 | UI 外壳与设计系统 | 中等 2/4 | **medium** | 设计令牌/双主题、导航与路由、仪表盘空状态、Mock 数据、i18n、Ctrl+K 基础 | `src/`、`index.html`、`package.json` |

**并行说明**：四个任务的代码目录互不重叠；唯一的共享点是 `backend/src/eclipse_health_backend/db/base.py`（B1-01 拥有）与模块路由挂载（B1-01 用 try/except 预留）。详细契约见各提示词与 `prompts/00-COMMON.md`。

### 难度口径

- **简单 1/4** → `low`：模板化、无架构决策。
- **中等 2/4** → `medium`：边界清晰，主要是实现与审美。
- **困难 3/4** → `high`：需要读现有代码/文档并对齐，存在数值或架构细节。
- **极难 4/4** → `max`（或 `xhigh`）：跨进程协议、生命周期、权限与审计，容易反复。

## 4. B1 接口与所有权矩阵

| 共享面 | 所有者 | 其他 Agent 的用法 |
|---|---|---|
| `backend/src/eclipse_health_backend/db/base.py`（engine/session/Base） | B1-01 | B1-02 只读导入，用于注册 `modules` / `audit_log` 模型 |
| `backend/src/eclipse_health_backend/app.py` | B1-01 | B1-02 只提供 `modules/api.py` 的 `router`；B1-01 用 try/except 挂载 |
| 领域模型（Member/Record/Signal…） | B1-01 | B1-03 不依赖；B1-02 只依赖 `records` 概念，不直接改模型 |
| `schemas/` | B1-02 | B1-01 / B1-03 只读；B1-04 不读 |
| `/api/v1` 前缀、端口 `8765` | B1-01 | B1-04 按此写 API client（可 Mock） |
| `src/` 全部 | B1-04 | 本批无人竞争 |
| `docs/`、`prompts/`、`uploads/` | 指挥官 | 所有 Agent 只读 |
| `reports/<id>-report.md` | 各 Agent 自己 | 只能写自己的报告 |

## 5. B1 验收门（轻量）

1. 四个 Agent 各自报告状态「完成 / 部分完成 / 阻塞」，并附验证命令与结果。
2. 指挥官在根目录跑一次：
   - `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`
   - `backend\.venv\Scripts\python.exe -m ruff check backend`
   - `npm run build`
3. 抽查 4 个关键点：`app.py` 路由与 DB、模块 Schema 与 echo 全链路、`analysis` 对 3 个样本的输出、UI 亮/暗两张截图。
4. 更新本文件：B1 状态、遗留问题、B2 任务表。

## 6. 风险与应对

| 风险 | 应对 |
|---|---|
| 模块系统范围膨胀 | B1-02 只做内核 + echo 示例；Samsung/真实模型放 B2 |
| 并行改动冲突 | 所有权矩阵 + 只读跨区 + 报告里列「需要的跨区改动」 |
| 数值不一致 | B1-03 以 `V2/发布预权重与评分信息/推理代码/inference.py` 为基准做对齐测试 |
| 文档与实现漂移 | 实现以 docs 为准；发现矛盾写进报告，指挥官统一改 docs |
| 上下文膨胀 | 报告 ≤80 行；指挥官不读全量代码，只读报告 + 抽查 |
| 健康数据外泄 | `uploads/` 与 `backend/.data/` 已 gitignore；Agent 不得联网上传 |

## 7. 需要用户提供

- Samsung / 华为 / Apple 手表导出样本 → `uploads/samples/<厂商>/`
- SCP-ECG 医院样本 → `uploads/samples/scp-ecg/`
- 第三方模型（ONNX / safetensors）→ `uploads/models/`
- 没有样本时，B2 的 Samsung 适配只能做「按文档的解析框架 + 夹具」，无法验证真实格式。

## 8. 启动方式

见 `prompts/README.md`。每个 Agent 会话只需一句：

> 阅读 `prompts/00-COMMON.md` 和 `prompts/0X-xxx.md`，严格按范围执行；完成后写 `reports/0X-xxx-report.md`。

## 9. B1 验收结果（2026-10-28）

**结论：通过，进入 B2。**

| 项 | 结果 |
|---|---|
| 后端测试 | 199 passed（core/api 80 + modules 68 + analysis 51） |
| ruff | `All checks passed!` |
| 前端构建 | `npm run build` 通过（JS 599.79 kB / gzip 189.82 kB，有 >500 kB 提示） |
| UI 截图 | 亮/暗 1440、1080、配色 B 共 4 张，风格达标 |
| 测试收集冲突 | 验收时修复：`tests/core/test_ids.py` → `test_domain_ids.py`，`tests/analysis/test_ids.py` → `test_analysis_ids.py` |

**B1 遗留、已定处理：**

- `jsonschema` 是模块内核直接依赖但未写入 `pyproject.toml` → B2-01 补为直接依赖；有 `uv` 环境后更新 lock。
- `app.py` 未在 lifespan 初始化/关闭模块宿主 → B2-01 接线。
- 模块连续崩溃自动禁用：采用契约的 **3 次**；B2-01 调整。
- 升级新增权限：**不自动授予、不自动回滚**；保留新版本，UI 提示用户授权。
- 安装 API 的本地路径参数只作调试；正式入口走导入/上传，B3 做 UI。
- `PATCH /records` 禁止改 `memberId`（保留现状）。
- 删除记录保留波形文件，30 天回收站清理（B3）。
- 多导联上传采用 `signals: [...]`（B2-02 契约）。
- Cardia 短记录默认抛异常；手表 30s 记录由调用方显式 `allowShortRecord=true` 并警告。
- measurements 持久化为规范行，API 返回完整对象；beats 增加 `probabilities`（B2 文档同步）。
- beats >50,000 暂用截断 + 警告；`beatsRef` 文件放 B3。
- 配色暂定 A 睡莲，设置页可切换；最终由用户定稿后再改规范文档。

**B1 暴露的关键风险：**

- **ONNX 会话初始化 141–165 秒**，已复现 4 次，且与 `graph_optimization_level` / 线程数无关；推理本身仅 0.1s。桌面端不可接受，列为 B2-01 第一优先级 spike。
- Cardia 2.0 以 64 搏为一块，30 秒手表记录通常 <64 搏；零填充可跑但需真实样本验证可靠性（等用户上传）。
- 当前 `uploads/` 无任何厂商样本，Samsung/Apple/华为/SCP-ECG 真实解析推迟到样本到位后。

## 10. B2 任务表（端到端贯通）

| 编号 | 任务 | 难度 | 建议思考强度 | 主要产出 |
|---|---|---|---|---|
| B2-01 | Cardia 模块化 + 分析 API + ONNX 启动性能 | 极难 4/4 | **max** | `analysis-model` 模块、分析入库/查询、引擎预热状态、性能报告 |
| B2-02 | 导入链路（WFDB/CSV）+ 参数校正 | 困难 3/4 | **high** | 格式识别、两步导入预览/提交、`ImportAdapter` 接口（为 Samsung 留位） |
| B2-03 | UI 端到端：记录详情 + 波形 + 分析结果 | 困难 3/4 | **high** | 真实 API、uPlot 波形、分析进度/摘要/测量/警告、拖拽导入 |
| B2-04 | 桌面壳 + 品牌启动动画 + logo | 中等 2/4 | **medium**（Tauri 卡住再升 high） | 单实例/托盘/窗口记忆、日食启动覆盖层、logo 四版本、sidecar dev 启动 |

**B2 完成定义（第一条端到端链路）：**

> 启动桌面应用 → 导入 `backend/resources/samples/100.hea`（或拖入 CSV）→ 确认采样率/导联 → 生成记录 → 点「分析」→ 看到进度 → 记录详情显示真实波形、R 峰、分类比例、HRV、质量与警告 → 结果已入库，重启后仍在。

## 11. B2 接口与所有权

- 接口契约：`docs/INTERNAL_API_V1.md`（B2 所有 Agent 必读）。
- B2-01 是**后端接线所有者**：`api/__init__.py`、`app.py`、`pyproject.toml`；B2-02 提供 `importers/api.py` 的 `router`，由 B2-01 挂载。
- B2-03 拥有 `src/**`，但**不碰** `src/main.tsx`、`src/branding/**`。
- B2-04 拥有 `src/main.tsx`、`src/branding/**`、`public/brand/**`、`src-tauri/**`、`package.json`（Tauri 插件）；不碰页面与设计令牌。
- 任务提示词见 `prompts/README.md` 的 B2 索引。

## 12. 待用户提供（B2 不阻塞，但影响 B3）

- Samsung / 华为 / Apple 手表导出 → `uploads/samples/<厂商>/`
- SCP-ECG 医院样本 → `uploads/samples/scp-ecg/`
- 真实 30 秒手表 ECG（用于验证短记录 + Cardia 可靠性）

## 13. B2 验收结果（2026-10-29）

**结论：通过，第一条端到端链路成立。**

| 项 | 结果 |
|---|---|
| 后端测试 | 275 passed（含 1 条真实 ONNX 慢测试） |
| ruff | `All checks passed!` |
| 前端构建 | `npm run build` 通过（766 kB / gzip 247 kB，>500 kB 提示） |
| 端到端 | 导入 MIT-BIH 100 → 分析 2270 搏 / 15 测量值 → 详情波形/单搏概率/质量/警告 → 重启后仍在 |
| 桌面 | `tauri dev` 启动、单实例、托盘、关闭到托盘、窗口记忆（退出后恢复待人工确认）均验证 |
| 品牌 | 日食启动动画亮/暗、logo 四版本、Tauri 图标完成；无白闪 |
| 验收修复 | 导入测试重复挂载路由的 warning；记录详情在仅有 summary 时的 `beats/measurements` 运行时崩溃 |

**关键进展：ONNX 根因已定位。** 动态形状子图导致 24,330 节点、会话初始化 ~150s；onnxsim 固定形状后 11,491 节点、**1.51s**，logits 最大差 1.9e-6（softmax 5e-7，远低于 1e-4 阈值）。本批先用后台预热绕过，**B3 批准采用简化模型**。

**B2 遗留决策（已定）：**

- 批准 onnxsim 产物作为 Cardia 模块自带权重；原模型保留回退；必须重跑 B1-03 对齐。
- `too_few_beats` 异步失败保持 POST 202 + 轮询 failed；UI 已处理。
- CSV 无单位必须确认 `unit`；非 360Hz 必须确认采样率（符合 G2 参数校正）。
- `.atr` 只存数量，不存位置；参考 R 峰不写入 metadata。
- 记录列表增加 `latestAnalysisStatus`（B3-02），避免前端 N+1。
- 长记录默认前 12 秒 + 一键全览；节律条 Overview 列 B3-02 的可选项，不强制。
- 关闭窗口默认收起到托盘；设置页开关与启动动画开关列 B4。
- 配色仍待用户定稿；logo/启动动画已走令牌，换色不改资产。

## 14. B3 任务表（功能与智能）

| 编号 | 任务 | 难度 | 建议思考强度 | 主要产出 |
|---|---|---|---|---|
| B3-01 | Cardia 简化模型 + 模块自带权重 + 启动 ≤3s | 中等偏难 3/4 | **high** | onnxsim 权重、模块打包、对齐复测、`/engine` 更新 |
| B3-02 | 趋势 + 记录状态 + 两条记录对比 | 困难 3/4 | **high** | `/trends` API、列表状态、趋势页、对比页 |
| B3-03 | 报告 PDF/PNG + 模板 + 历史 | 困难 3/4 | **high** | 报告生成/存储/下载、简洁/详细/医生版、脱敏水印 |
| B3-04 | LLM 助手 + 工具调用可视化 | 极难 4/4 | **max** | 多厂商/Ollama、流式、工具追踪、透明面板、会话历史 |

**B3 完成定义：**

> 应用里能看到趋势曲线；能把两条记录并排比较；能为一条记录生成 PDF 与 PNG 分享卡并再次下载；能配置一个 LLM（或 Ollama）就自己的记录提问，并看到每次工具调用的参数与“发送了什么”。

## 15. B3 接口与所有权

- B3-01：`modules/official/cardia/**`、`scripts/pack_cardia.py`、`analysis/model.py`（仅模型选择）、`backend/resources/models/cardia/`（新增简化权重）、`backend/tests/analysis/**`。
- B3-02 是**前端共享层所有者**：`src/App.tsx`、`src/lib/api/{client,types,queries,adapters}.ts`、`src/lib/i18n/*`、记录列表/趋势/对比页面与组件；后端 `trends/`、`api/trends.py`、`api/records.py`（加字段）。
- B3-03：后端 `reports/`（生成/存储/下载）、`api/reports.py`、测试；前端 `src/pages/reports.tsx`、`src/features/reports/**`（含 feature-local i18n bundle），不改共享 i18n。
- B3-04：后端 `llm/`、`api/assistant.py`、`db/assistant_repo.py`、测试；前端 `src/pages/assistant.tsx`、`src/features/assistant/**`（含 feature-local i18n bundle）。
- 共享文件冲突用「feature-local i18n bundle + feature-local API 文件」解决；不要改别人的页面/组件。

## 16. B3 风险

| 风险 | 应对 |
|---|---|
| PDF 中文字体/排版 | 选无原生 GTK 依赖的方案（ReportLab / 前端 react-pdf 二选一）；先做 1 页样张再扩展 |
| LLM Key 安全 | Windows 凭据管理器（`keyring`）；无 Key 时用本地 mock/Ollama 演示 |
| 报告与趋势数据口径 | 统一取 `measurements` 的 code；缺值显示「无数据」而不是 0 |
| 两个 UI Agent 冲突 | B3-02 独占共享层；B3-03/04 只加 feature 目录与 feature-local i18n |
| 简化模型数值漂移 | 对齐测试 + 原模型回退开关；差异 >1e-4 立即回退 |

## 17. B3 验收结果（2026-10-29）

**结论：通过。核心 MVP 主干已打通。**

| 项 | 结果 |
|---|---|
| 后端全量 | **357 项全部通过**（1 个可选 Ollama 用例 skipped） |
| ruff | `All checks passed!`（backend + modules/official + scripts） |
| 前端构建 | `npm run build` 通过 |
| 启动性能 | ONNX 初始化 1.19–1.35s；模块预热 2.4–2.7s；`/engine` ready 约 6s（含首次安装） |
| 数值对齐 | 原图 vs 简化图逐搏概率最大差 1.8e-7 / 3.8e-7 / 4.4e-7（100/200/208） |
| 趋势/对比 | 5 条不同日期记录、状态徽标、趋势点跳转、并排对比均实测 |
| 报告 | simple 1 页 / detailed 2 页 / doctor 2 页 / PNG 1080×1350；脱敏/水印/历史/下载/删除均实测 |
| 助手 | mock 全链路：3 次工具调用 → 回答；透明面板、工具 JSON、会话持久化、DPAPI key |
| 验收修复 | `ReportsPage` 路由仍指向占位页 → 已改到真实页面；`tests/reports/test_api.py` 与 `tests/modules/test_api.py` 同名 → 改为 `test_reports_api.py` |

**B3 遗留、已定处理：**

- `api/__init__.py` 的 trends/reports/assistant 挂载已共存；`db/base.py` 已注册 assistant 表。
- `modules/host.py` 白名单未放行 `EH_CARDIA_MODEL`：原图回退只对直调生效；B4 补一行。
- `backend/pyproject.toml` 未声明 matplotlib/Pillow/Jinja2（venv 已装）：打包前补声明。
- B3-03 的 `src/features/reports/preview.html|tsx` 是开发预览入口：B4 删除或保留由用户定。
- B3-02 `latestAnalyzedAt` 用分析创建时间；精确完成时间需加 `completed_at` 列，B4 可选。
- 对比页暂不进左侧导航；B4 视用户反馈决定。
- LLM 只实测 mock；真实 Ollama/OpenAI/Anthropic 需要用户提供 key/本地模型后联调。
- 首包 1.17MB（gzip 365KB）：B4 做路由级 `React.lazy` 分包。

## 18. 整体进度（对照 44 项已确认功能）

**主干完成度约 80%。** 已确认的 44 项中，约 30 项完成或基本完成；剩余 14 项以「广度 + 收口」为主，不是架构难题。

| 组 | 已完成 | 未完成 / 半成品 |
|---|---|---|
| A 首次体验 | A2 拖拽、A3 空状态、A4 命令面板、A5 骨架 | A1 真实示例记录（当前 mock）、A6 全局快捷键（仅波形/Ctrl+K） |
| B 波形 | B1 缩放平移、B2 单搏概率、B4 质量标色 | B3 心搏列表、B5 12 导联网格（仅展示，模型仍单导联）、B6 节律条、B7 波形 PNG |
| C 分析 | C1 进度、C2 摘要、C3 解释、C4 警告、C6 模型卡、C7 重新分析 | C5 危急值提示条、C7 切换引擎（仅 Cardia） |
| D 记录 | D1 列表/筛选、D2 标签/备注、D3 趋势、D4 对比 | D5 导出/备份、D6 隐私中心、D1 收藏、D2 症状/用药 |
| E 报告 | E1/E2/E3/E4/E6 全部 | —（E5 已确认暂不加入） |
| F LLM | F1–F6 全部（mock 验证） | 真实 provider 联调（需 key/Ollama） |
| G 输入 | G1 WFDB/CSV、G2 参数校正 | G1 EDF、G3 三种手表格式（需样本）、G4 SCP-ECG（需样本） |
| H 桌面 | H1 托盘/单实例、H2 窗口记忆/主题、H3 DPAPI key | H1 通知、H5 自动更新、H6 诊断日志导出 |
| I 模块/健康 | I1 模块内核 | I1 模块安装/权限 UI、I2 手动指标、I3 健康档案 |

## 19. B4 候选（按优先级）

1. **打包/安装包**（必须，且不受 UI 反馈影响）：PyInstaller sidecar + Tauri 安装包 + 冒烟测试。
2. **数据收口**：D5 导出/备份、D6 隐私中心、H6 诊断日志；设置页加「关闭到托盘 / 启动动画」开关。
3. **波形增强**：B3 心搏列表跳转、B6 节律条、B7 波形 PNG、B5 12 导联展示（分析仍单导联）。
4. **模块 UI**：安装/卸载/权限授权页面，接 B1-02 内核。
5. **设备格式**：Samsung/华为/Apple/SCP-ECG，等 `uploads/` 样本到位后逐格式验证。
6. **健康档案/手动指标**：I3 档案、I2 血压/体重/血氧录入。
7. **收尾**：路由 lazy、真实 Ollama/API 联调、自动更新（H5）、通知（H1）。

> 建议节奏：先让用户实际试用当前版本并提意见；同时只并行一个「打包」Agent。剩余功能等反馈后再排，避免返工。

## 20. B4 一次性收口计划（2026-10-29 用户要求）

用户要求「一次性尽量做完，不多轮迭代」，并授权 Agent 联网下载公开样本。B4 改为两波 8 个 Agent（内存/端口限制），不是多轮产品迭代。

### Wave 1

| 编号 | 任务 | 难度 | 思考强度 |
|---|---|---|---|
| B4-01 | PyInstaller sidecar + Tauri 安装包 + 通知/设置命令/更新占位 | 困难 3/4 | high |
| B4-02 | 公开样本与格式资料采集（EDF/SCP-ECG/Apple/Samsung/华为） | 中等 2/4 | medium |
| B4-03 | 设备/医院格式适配器（真实样本验证优先，缺样本标 experimental） | 困难 3/4 | high |
| B4-04 | 导出/备份 + 隐私中心 + 诊断日志 + 设置（后端路由接线所有者） | 困难 3/4 | high |

### Wave 2

| 编号 | 任务 | 难度 | 思考强度 |
|---|---|---|---|
| B4-05 | 心搏列表 / 节律条 / 12 导联展示 / 波形 PNG / 快捷键 | 困难 3/4 | high |
| B4-06 | 模块安装 / 权限 / 审计 UI | 中等偏难 3/4 | high |
| B4-07 | 健康档案 + 手动指标 + 通知 | 中等偏难 3/4 | high |
| B4-08 | LLM 真实联调（Ollama 优先）+ 助手收尾 | 困难 3/4 | high |

### 明确的能力边界（做不到的部分）

- **12 导联分析**：Cardia 2.0 是单导联模型；B4-05 只做展示，分析仍用 MLII/第一导联。要 12 导联分析必须换模型，不在本批。
- **自动更新**：B4-01 只做插件配置与本地验证；真正上线需要签名私钥 + 更新服务器（用户提供 GitHub Release/静态 URL 后启用）。
- **外部 LLM**：B4-08 优先本机 Ollama；没有 Ollama/API Key 时以 mock 交付，真实外部 provider 联调需要用户提供 Key。
- **华为/部分 Samsung 样本**：公开样本可能不存在；B4-02 尽力下载，B4-03 对无真实样本的格式标 `experimental`，真实设备兼容性需用户后续提供导出文件验证。
- **SCP-ECG**：完整标准较大，B4-03 做最小可用解析（常见 section），复杂变体可能失败并明确报错。

### B4 完成定义

> 安装包可双击启动；导入 WFDB/CSV/EDF/SCP-ECG/Apple/Samsung/华为（后三者按样本能力标注）；记录详情有心搏列表/节律条/12 导联展示/PNG；趋势/对比/报告/助手可用；导出/恢复/隐私清空/诊断包可用；模块可安装/授权/卸载；档案与手动指标可录入；真实 Ollama 或 mock 助手可用；全量测试/build 通过。

### 收尾（指挥官统一做，不再单开 Agent）

- 接线检查、全量 pytest/ruff/build、真机冒烟、路由懒加载、`pyproject` 依赖声明、README、git checkpoint。
- 如果某格式确实拿不到样本：在报告中明确「代码完成但未真机验证」，由用户决定是否补样本。

## 21. 第三方模块接入现状（2026-10-30）

详见 `docs/MODULE_DEVELOPER_GUIDE_V1.md` 与 `prompts/40-module-author-template.md`。

**结论：**

- **能装、能启停、能授权、能审计、能通过 `/api/v1/modules/{id}/rpc` 调用**：已成立。
- **自动接进主界面/导入/分析/报告/LLM 工具**：除内置 Cardia 分析外，尚未接线。
  - `analysis-model`：`analysis_service/bridge.py` 写死 Cardia 模块 ID/引擎/方法，无通用引擎注册。
  - `device-adapter`：`importers/registry.py` 只注册内置适配器，manifest `importFormats` 未消费。
  - `exporter` / `ai-tool` / UI / theme / locale：无 contribution loader。
- 当前模块与核心共用 Python 环境、无 OS 沙箱、签名未验证；只应安装可信模块。

**要把第三方功能真正接进 UI/流水线，核心还缺（按优先级）：**

1. 通用 `analysis-model` loader + 引擎选择（1–2 天）
2. `device-adapter` 模块桥（1–2 天）
3. `ai-tool` registry（0.5–1 天）
4. `exporter` registry（约 1 天）
5. 模块数据目录/核心数据回调（`records.*` 目前返回 `NOT_IMPLEMENTED`）
6. per-module venv / 沙箱 / 签名 / 在线注册表
7. 声明式 UI 渲染器（3–5 天）

**给第三方的现成路径：** 先写纯 RPC 模块（安装/启动/调用闭环），按 `prompts/40-module-author-template.md` 自测；需要出现在 UI 时再由核心补对应 loader。

## 22. B4 后进度评估（2026-10-30，供用户决策）

**按最初 44 项已确认功能计：约 90% 完成。**

| 分类 | 数量 | 说明 |
|---|---|---|
| 已完成/基本完成 | 39 | 含 A2–A6、B1–B7、C1–C6、D2–D6、E1–E4/E6、F2/F3/F5/F6、G1/G2/G4、H1/H2/H6、I2/I3 |
| 部分完成 | 4 | A1 真实示例记录、C7 切换引擎、D1 收藏、G3 真机格式验证 |
| 未完成 | 1 | H5 自动更新（缺签名私钥 + 更新服务器） |

**B4 任务状态：**

- B4-01 打包：**完成**，NSIS 安装包 211.5MB，安装/启动/分析/退出已验证。
- B4-02 样本：**部分完成**，EDF/SCP-ECG 有真实公开样本；Apple/Samsung/华为无公开原始导出。
- B4-03 格式适配器：**完成**（EDF/SCP 真实样本验证；三家厂商 `experimental`）。
- B4-04 导出/隐私/诊断/设置：**完成**。
- B4-05 波形增强：**完成**（心搏列表/节律条/12 导联展示/PNG/快捷键/质量区段）。
- B4-06 模块安装/权限/审计 UI：**完成**（80 项模块测试）。
- B4-07 档案/手动指标/通知：代码已落地并接线，**报告未到**，最终验收时确认。
- B4-08 LLM 真实联调：**未开始**；assistant 仍是 mock 验证，真实 provider 需 Ollama/API Key。

**剩余收口（不依赖第三方模块 glue）：**

1. A1 真实示例记录/首次引导 —— 低，2–3h。
2. D1 收藏 —— 低，2h。
3. C7 切换引擎 —— 中，需第二个可用引擎（1–2 天）。
4. 最终 QA：全量测试/build、安装包冒烟、路由懒加载、依赖声明、README —— 约 1 天。
5. **H5 自动更新** —— 阻塞：需要签名私钥 + 更新服务器，Agent 无法独自完成。
6. **G3 真机格式** —— 阻塞：需要用户提供 Apple/Samsung/华为真实导出；代码已就绪，标 `experimental`。

> 结论：不做第三方模块 glue，也能在约 1 个短批次内把原始目标收到 ~95%；最后 5% 的 H5/G3 需要用户提供基础设施或样本。

## 23. 第三方 Agent 平台（#1–#4）排期（2026-10-30）

用户确认把以下四类加入计划，不做 #5（每模块独立运行时/任意 UI）：

1. ONNX 推理模型
2. 首页显示卡片
3. 工具型 Agent
4. 带自有数据的领域 Agent（慢病/饮食）

**总量：3 轮 × 4 Agent（12 个位置），约 2–3 周。**
第 3 轮含验收/打包/文档，不全是新功能；若只做 #1–#2，2 轮约 1 周。

### 第 1 轮 · 平台底座 + 原目标收口

| 位置 | 任务 | 说明 |
|---|---|---|
| R1-1 | 平台 v2 底座：manifest 扩展（widgets/pages/tools/recordTypes）、贡献注册表、loader、schema 测试 | 关键路径；先写契约文档再并行 |
| R1-2 | 模块数据 API：`records.*` 核心回调、模块数据隔离、权限/审计、测试 | 领域 Agent 的前提 |
| R1-3 | ONNX 分析 loader（#1）：引擎注册/选择、ONNX runner、预处理管线、结果映射、C7 第二引擎 | 覆盖大多数第三方推理 |
| R1-4 | 原目标收口：A1 真实示例记录、D1 收藏、B4-07 验收 | 低风险，顺带完成 |

### 第 2 轮 · 展示、工具、领域 Agent

| 位置 | 任务 | 说明 |
|---|---|---|
| R2-1 | 首页 widget v1（#2）：8 种受控组件、语义令牌映射、数据源、示例、截图 | 第三方只交 JSON |
| R2-2 | 工具注册表（#3）：模块 tools → 助手工具表、RPC tool.call、权限、透明面板 | 慢病/饮食 Agent 的入口 |
| R2-3 | 模块页渲染器（#4 UI）：表单/表格/详情/列表、受控组件、模块数据 | 领域 Agent 的页面 |
| R2-4 | 示例领域 Agent（#4）：一个真实 `health-domain` 模块（体重/血压或饮食），含数据 schema、worker、widget、tools、page | 端到端验证 #1–#4 |

### 第 3 轮 · 集成、验收、发布

| 位置 | 任务 | 说明 |
|---|---|---|
| R3-1 | 集成 owner：贡献接线、跨 Agent 修复、全量测试/build、路由懒加载 | 关键路径 |
| R3-2 | 端到端验收：安装示例模块 → 首页卡片 → 助手工具 → 引擎选择 → 数据 CRUD → 升级/卸载 | 真机截图 |
| R3-3 | 安装包重打 + 冒烟（新平台/模块随包） | 重新生成 NSIS |
| R3-4 | 文档/Agent 模板 + B4-08 LLM 真实联调（有 Ollama/Key 则测，否则报告） | 收尾 |

**依赖与风险：**

- 第 1 轮 R1-1 必须先出契约；R1-2/3 可并行写，R2 全部依赖 R1-1/R1-2。
- 每模块独立运行时（#5）不做；遇到必须额外 Python 库的模块，要求作者导 ONNX 或自包含 exe，否则阻塞并单独评估。
- H5 自动更新、G3 真机格式仍需要用户提供签名服务器/样本，不计入这 3 轮。
- 示例领域 Agent 选哪个（体重/血压 vs 饮食）需用户定；建议先用「体重/血压」验证数据+卡片+工具，饮食涉及食物库/联网，放后。 

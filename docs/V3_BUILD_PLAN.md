# eclipse health v3 · 总控计划

> 更新：2026-10-28 · 指挥官文件 · B1 完成 / B2 准备中
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
| 版本控制 | 当前不是 git 仓库（建议 Agent 跑完后 `git init` 建基线，便于回滚与审查） |

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

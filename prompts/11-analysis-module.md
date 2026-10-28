# B2-01 · Cardia 模块化 + 分析 API + 启动性能

> 难度：极难 4/4 · 建议思考强度：**max**（不可用用 xhigh） · 批次：B2 贯通
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 本批的硬目标是「导入 → 分析 → 入库」跑通；性能 spike 是同一任务的第一优先级，不另开方向。

## 1. 必读

- `docs/INTERNAL_API_V1.md`：§3 分析接口、§4 数据形状、§0 通用。
- `docs/MODULE_CONTRACT_V1.md`：§2 manifest、§3 `analysis-model`、§4 生命周期、§5 RPC、§6 权限、§12 错误码。
- `docs/DATA_SCHEMA_V1.md`：§6 AnalysisResult、§7 Measurement、§8 Beat、§11 存储。
- `reports/01-backend-core-report.md`、`reports/02-module-system-report.md`、`reports/03-cardia-engine-report.md`。
- 代码：`backend/src/eclipse_health_backend/modules/`、`analysis/`、`api/`、`db/`。

## 2. 目标

把 Cardia 2.0 变成第一个真正的 `analysis-model` 模块，并由核心提供「发起分析 / 查询结果 / 引擎状态」API；结果持久化，重启后仍可查。**同时**解决或明确绕过 ONNX 会话初始化 141–165 秒的问题。

## 3. 你必须交付

1. **ONNX 启动性能 spike（先做，限时约 60 分钟）**
   - 已复现：同一进程两次 `InferenceSession` 分别 141.8s / 148.8s；`ORT_DISABLE_ALL` + 单线程仍 164.5s；推理本身 0.1s。说明不是图优化/线程数。
   - 排查方向（按成本从低到高）：
     1. 模型图规模：用 `onnx`（临时安装到临时 venv 或 `--target`，不要污染项目依赖）统计节点数/op 类型；若节点数异常大，记录结论。
     2. ORT provider：当前有 `AzureExecutionProvider` + `CPUExecutionProvider`；尝试禁用/移除 Azure EP、设置 `providers=["CPUExecutionProvider"]`（已做）、`SessionOptions` 各项。
     3. ORT 版本：在**临时 venv** 里试 1.20 / 1.22 / 1.24 的 session 初始化时间；不要把项目依赖降级。
     4. 模型简化：`onnxsim` / `onnxoptimizer` 在临时环境生成简化模型，测初始化 + 数值差异。
     5. 系统因素：Defender 实时扫描、中文路径、磁盘；给出可验证结论。
   - **产出**：`reports/B2-01-ort-spike.md`（≤60 行）：根因假设、实测数据、是否可修、建议。若不能修，实现「后台预热 + `GET /engine` 状态 + UI 明确提示」，并测量冷启动到 ready 的真实时间。
   - 允许修改 `analysis/model.py` / `analysis/engine.py` 以支持 session options / 预热，但**不得改变推理数值**；B1-03 的对齐测试必须继续通过。

2. **Cardia 模块**
   - `modules/official/cardia/`：`module.json`（`type: "analysis-model"`、`contributes.models`、权限最小集）、`src/main.py`、`checksums.json`、`README.md`。
   - Worker JSON-RPC：`initialize` 返回能力/模型卡摘要/健康状态；`analyze` 接收 `{recordId, signalRef:{path,sha256,fs,lead,unit,nSamples}, options:{allowShortRecord}}`，读取临时 float32 文件，调用 `analysis.analyze`，返回 AnalysisResult；`health`；`shutdown`。
   - 大数组必须走**临时文件句柄**，不要把 650k float32 塞进一行 JSON（宿主单条上限 4MB）。核心负责写临时文件并清理。
   - 模型卡：参数量、输入契约（单导联/360Hz/64 搏）、类别、评测来源、适用范围、非诊断声明；放 manifest/README，并由 `GET /engine` 暴露摘要。

3. **核心分析服务**
   - `analysis_service/`：负责启动/复用 Cardia worker、写信号临时文件、调用 RPC、把结果写入 `analyses/measurements/annotations`（beats 内联 JSON，≤50k）、状态机与错误映射。
   - 若模块不可用，提供**同进程直调** fallback（仅调试开关 `EH_ANALYSIS_DIRECT=1`），保证 B2 不被模块问题卡死；默认走模块。
   - 生命周期：`app.py` lifespan 调 `init_module_system()` / `shutdown_module_system()`；启动后**后台线程**预热 Cardia（不要阻塞 HTTP 就绪）。
   - 记录不存在/无信号/too few beats/模块崩溃 → 契约错误码；分析失败要落库 `status=failed` + `error`。
4. **API（`backend/src/eclipse_health_backend/api/analyses.py`）**
   - 按 `docs/INTERNAL_API_V1.md` §3 实现：发起、按记录列表、按 ID 查询（含/不含 beats）、beats 分页、`GET /engine`。
   - `POST` 同一记录已有 `queued|running` 时幂等返回该分析（写进 OpenAPI 描述）。
   - `progress.stage` 可粗粒度：`quality→features→inference→measurements→summary`；没有真实回调时按阶段推进。
5. **接线与依赖**
   - 你是后端接线所有者：`api/__init__.py`、`app.py`、`backend/pyproject.toml`。
   - 挂载 B2-02 的导入路由：`from ..importers.api import router as imports_router`，try/except 挂到 `/api/v1`（它不存在时服务照常启动）。
   - 把 `jsonschema` 写为直接依赖（当前是传递依赖）；有 `uv` 时更新 lock，没有就在报告注明。
   - 模块连续崩溃自动禁用改为 **3 次**（契约 §5），与 B1-02 现状不同，改完补测试。
6. **测试**
   - `backend/tests/analysis_service/`：模块打包→安装→启动→analyze（sample 100）→结果结构/概率和/持久化→重启后查询；`too_few_beats`；模块崩溃→failed；引擎状态 warming→ready；直调 fallback。
   - 不依赖网络；用临时 `EH_DATA_DIR`；ONNX 测试可标记 `slow`，但 CI 默认要能跑（可用 fixture 复用 session）。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/analysis_service/**
backend/src/eclipse_health_backend/api/analyses.py
backend/src/eclipse_health_backend/api/__init__.py
backend/src/eclipse_health_backend/app.py
backend/src/eclipse_health_backend/db/analysis_repo.py
backend/src/eclipse_health_backend/analysis/model.py        # 仅性能/预热，不改数值
backend/src/eclipse_health_backend/analysis/engine.py       # 仅性能/预热，不改数值
modules/official/cardia/**
scripts/pack_cardia.py
backend/tests/analysis_service/**
backend/pyproject.toml
```

不要动：`modules/` 其他目录、`importers/`、`api/records.py`、`domain/`、`src/`、`src-tauri/`、`docs/`、`prompts/`、`uploads/`。

## 5. 与 B2-02 的契约

- 它提供 `backend/src/eclipse_health_backend/importers/api.py` 的 `router`（路径以 `/imports/...` 开头）；你负责 `app.include_router(..., prefix="/api/v1")`。
- 它不碰 `api/__init__.py` / `app.py`。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
# GET /api/v1/engine 直到 ready；POST /api/v1/records/{id}/analyses；轮询 GET /api/v1/analyses/{id}
```

报告写：ORT spike 结论、冷启动到 ready 时间、全链路命令、分析耗时、持久化验证、未做项。

## 7. 明确不做

Samsung/Apple/华为/SCP-ECG、报告 PDF、趋势、LLM、模块安装 UI、每模块 venv、签名、SSE/取消、12 导联、beatsRef 文件。只做「Cardia 模块 + 分析 API + 入库 + 启动性能」。

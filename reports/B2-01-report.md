# 报告 · B2-01 Cardia 模块化 + 分析 API + 启动性能

状态：完成

## 交付

- `modules/official/cardia/`：`module.json`（`analysis-model`、`contributes.models` 模型卡、最小权限
  `files:user-selected`）、`src/main.py`（stdio JSON-RPC：`initialize`/`warmup`/`health`/`analyze`/
  `deactivate`；波形走临时 float32 文件 + sha256；结果 >3.5MB 转 `resultRef` 文件）、`README.md`、
  `checksums.json`；`scripts/pack_cardia.py` → `dist/cardia-1.0.0.ehmod`（4 文件，自校验）。
- `analysis_service/`：`service.py`（单线程队列、状态机 quality→inference→measurements→summary、
  临时文件写入与清理、`EH_ANALYSIS_DIRECT=1` 直调 fallback、后台预热状态机、重启遗留任务回收）、
  `bridge.py`（自动安装/懒启动/预热轮询/`analyze` RPC/`resultRef` 读取）。
- `db/analysis_repo.py`：`analyses`（完整结果 + beats 内联 ≤50k）、`measurements`、`annotations`
  持久化；摘要 / 详情 / 逐搏分页。
- `api/analyses.py`：`POST /records/{id}/analyses`（202，同记录 queued|running 幂等）、
  `GET /records/{id}/analyses`、`GET /analyses/{id}?includeBeats=`、`GET /analyses/{id}/beats`、
  `GET /engine`（含模型卡摘要）。
- `app.py` / `api/__init__.py`：lifespan 启停模块系统与分析服务；运行时挂载 B2-02 导入路由
  （缺失时照常启动）。
- `analysis/model.py`：`prewarm()`、会话初始化耗时记录、`EH_ORT_OPT_LEVEL` / `EH_ORT_*_THREADS`
  调试参数；推理数值路径未改。
- `backend/pyproject.toml`：`jsonschema` 改为直接依赖、注册 `slow` marker。
- 模块崩溃自动重启预算 1 → **3**（契约 §5），补测试。

## 验证

- `ruff check backend scripts modules/official` → All checks passed。
- `pytest backend/tests -q` → **275 项全部通过**（exit 0；含 1 条 `slow`：真实 ONNX 模块全链路）。
  注：本机 pytest 配 `-q` 时不打印汇总行，以 exit code 与进度点为据。
- 慢测试实测（空闲）：预热 **158.6s**、POST→completed **3.5s**、**2270** 搏、**15** 个测量值；
  短记录 → `failed/too_few_beats`；新 TestClient（模拟重启）后结果与 beats 一致。
- 端到端（真实 uvicorn + 空数据目录，自动安装模块）：`/engine` warming→ready（本次 392.6s，
  另有 Agent 并行跑测试导致 CPU 争用；空闲实测 158.6s）；`POST` 202 → 8.5s 完成；
  2270 搏、15 测量值、概率和 1.0、`beatsTotal`/分页/记录列表均正确；15 行 measurements 落库。
- 持久化：进程重启后 `GET /analyses/{id}` 仍返回 completed + 全部逐搏。
- ONNX spike：`reports/B2-01-ort-spike.md`（根因 + 150s→1.5s 的修复方案与数值数据）。

## 未做 / 偏离

- **未启用简化模型**：onnxsim 可把初始化从 ~190s 降到 1.5s，但 logits 差 1.9e-6，属「改变推理数值」，
  且模型文件在 `backend/resources/`（非本批所有权）——见 spike 报告，等指挥官放行。
- Cardia 结果 `annotations` 为空；annotations 表写入路径已实现并有单测，但当前无数据可写。
- beats >50k 截断 + 警告，未做 `beatsRef` 文件（与 B1-03 一致）。
- 全进程单队列串行（不同记录的两次分析也排队）；多导联记录优先取 MLII 再取第一条。
- `too_few_beats` 等异步失败只体现在轮询结果（POST 仍 202）；同步只校验记录/信号/引擎。
- 模块与核心共用同一 Python 环境与 `analysis` 库（B3 每模块 venv 后拆开，RPC 不变）。
- 崩溃后仍停在 `crashed` 需手动 `start`，未做 `enabled=false` 自动禁用。
- 测试进程（`PYTEST_CURRENT_TEST`）不自动预热，避免拖慢其他套件；生产启动自动预热。
- 无 uv（环境无 pip/uv），未更新 lock；`jsonschema 4.26.0` 已在 venv 中。
- 跨区改动 2 处（见下）：`modules/constants.py` 一行 + `tests/modules/test_lifecycle.py` 一行。

## 跨区需求（需要别的 Agent 或指挥官处理）

- B2-02：`tests/imports/conftest.py` 用 `app.routes` 探测 imports 是否已挂载；FastAPI 0.162 的
  `include_router` 生成惰性 `_IncludedRouter`（无 `.path`），探测不到导致重复挂载 →
  `Duplicate Operation ID` 警告。建议改用 `app.openapi()["paths"]` 或直接信任 B2-01 已挂载。
- B2-03：`record-detail.tsx` 的 `completedAnalysis?.beats.length` 在详情未就绪时会取到列表项
  （无 `beats` 字段）→ 运行时 TypeError；列表项已新增 `beatsTotal`，用它判断。
- 共享 `client` 夹具的测试若访问模块 API：`reset_db()` 会连模块注册表一起删，需在 reset 后
  重新 `init_module_system()`（本批 e2e 测试已这样处理）。
- 跨区改动说明：`modules/constants.py` 的 `MAX_AUTOMATIC_RESTARTS=3` 与随之调整的
  `tests/modules/test_lifecycle.py`（仅加 `manager.max_restarts = 1` 保持原测试语义）。

## 需要指挥官决策

- 是否批准用 onnxsim 简化权重（启动 150s→1.5s，数值差 1.9e-6；建议随模块 `models/` 发布）。
- `too_few_beats` 等异步失败不返回 422 是否接受（当前 POST 202 + 轮询 failed）。
- 模型卡参数量口径：ONNX initializer 元素数 ≈722k（导出按窗口展开会重复常量）。

## 建议下一批

- B3：每模块 venv，把 `analysis` 库与权重移入 Cardia 模块包；简化 ONNX 并重跑对齐；
  `beatsRef`、SSE/取消、批量分析、模块安装/授权 UI 接线。

## 全链路命令

```powershell
backend\.venv\Scripts\python.exe scripts\pack_cardia.py        # -> dist/cardia-1.0.0.ehmod
$env:EH_DATA_DIR="C:\tmp\eh-data"                              # 可选；默认 backend/.data
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
# GET  /api/v1/engine                      -> warming ... 直到 ready（首次约 160s，后台预热）
# POST /api/v1/records/{id}/analyses       -> 202 {analysisId}
# GET  /api/v1/analyses/{analysisId}       -> completed + beats/measurements
```

# 报告 · B5-02 C7 通用引擎列表 + 选择 + 重新分析

状态：完成

## 交付

- 后端注册表：`analysis_service/engines.py` 新增 `EngineDescriptor` / `list_engines()` / `get_engine(id)`；当前仅注册 `cardia`，字段取自 `bridge.py` 常量。`CARDIA_ENGINE` 等导出保持不变。
- `GET /api/v1/analyses/engines` → `{"items":[{id,name,moduleId,modelId,modelVersion,available,reason}]}`；路由放在 `/analyses/{id}` 之前，避免被吞。
- `POST /records/{id}/analyses` 改为注册表校验：未知引擎 → `unknown_engine`，`details.supported` 来自注册表；删除写死的 `SUPPORTED_ENGINES`。
- 重新分析：沿用服务层既有逻辑——同记录存在 `queued|running` 时幂等复用，`completed|failed` 后新建一条；补测试显式覆盖并校验指定 engine。
- 前端新增 `src/features/analysis/`：`engine-catalog.ts`（直连 `baseUrl`，本地类型 + 容错归一化）、`use-engine-catalog.ts`（React Query，60s 缓存，仅网络错误重试）。
- `record-detail.tsx` 移除 `engine:"cardia"` 硬编码；默认第一个可用引擎，目录变化时自动回退；重新分析前可改选。
- `analysis-panel.tsx`：多引擎显示 `Select`，单引擎显示只读「名称（modelId modelVersion）」+「更多引擎可通过安装分析模块获得」；显示「当前分析：engine · modelId modelVersion」与重新分析说明；目录加载失败可重试，无可用引擎时禁用开始按钮。
- i18n 只新增 `analysis.engine.*`（current/selectLabel/loading/catalogError/option/single/moreHint/noAvailable）与 `recordDetail.reanalyzeHint`，zh-CN / en-US 同步。

## 验证

- `backend\.venv\Scripts\python.exe -m ruff check backend` → All checks passed（全后端）。
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/analysis_service -q` → 26 passed（新增 6 条引擎注册表测试）。
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/analysis_service backend/tests/analysis backend/tests/api -q` → 127 passed。
- 全量 `pytest backend/tests -q` → 全绿，3 skipped（真实 ONNX 相关）。
- `npm run build` → tsc + vite 通过（2.80s）；`npx tsc --noEmit` 通过。
- UI（真实后端 + 内置 MIT-BIH 100 记录，1440×1100）：
  - 单引擎：无下拉框，显示只读引擎文本与说明；亮/暗各一张 `reports/screenshots/B5-02-light.png`、`B5-02-dark.png`，控制台 0 error。
  - 测试期用 Playwright 拦截把目录 mock 成两个引擎：下拉框出现，选中第二引擎后「重新分析」请求体为 `{"engine":"cardia-onnx","options":{"allowShortRecord":false}}`，控制台 0 error；截图 `B5-02-multi-engine.png`。

## 未做 / 偏离

- 测试目录：提示词写 `backend/tests/analyses/**`，仓库实际不存在该目录；测试放在既有分析 API 测试目录 `backend/tests/analysis_service/test_engine_catalog.py`，未新建并行目录。
- 未知引擎状态码：现有 `InvalidInputError` 约定为 **422**（原测试也断言 422），未按提示词改成 400，以免破坏既有 API 契约。
- `available` 目前只按内置模型文件是否存在判断，且仅用于 UI 禁用/说明；POST 只拒绝「未注册」引擎，不拒绝 `available=false`，避免打包后源目录缺失时误伤已安装模块。
- 现有运行状态接口实际路径是 `GET /api/v1/engine`（非提示词所写 `/analyses/engine`），保持原样未动。
- 未实现第二引擎、未改 ONNX/Cardia 推理、未改 `src/lib/api/**`。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `src/lib/api/types.ts` 的 `AnalysisResult` 未声明后端已返回的 `engine` 字段；本批只能从 `parameters.engine` 读取。建议 B5-01 在类型/适配器中补上，后续可直接读 `analysis.engine`。
- 第二引擎接入时应扩展 `engines.py` 的 `list_engines()`（平台 #1 ONNX loader），前端无需改动。

## 需要指挥官决策

- 未知引擎最终该用 400 还是沿用全局 422？（本批沿用 422。）
- 是否要求 POST 拒绝 `available=false` 的引擎（当前只做目录展示）。

## 建议下一批

- 平台 #1 ONNX 加载器落地第二个引擎；引擎目录随模块安装/卸载刷新（安装模块后 invalidate `["analysis","engines"]`）。
- 记录详情补「分析历史」切换（当前只默认最新一条，重新分析后旧结果仍在库中可见但 UI 未列出）。

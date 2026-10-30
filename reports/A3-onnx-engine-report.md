# 报告 · A3 <平台 #1：通用 ONNX 分析引擎 loader（第二引擎）>
状态：完成

## 交付
- `analysis_service/engines.py`：引擎目录新增模块引擎。ID 规则 `<moduleId>:<modelId>`；只扫描已安装且 enabled 的 `analysis-model` 模块的 `contributes.models[]`（`format="onnx"`）。内置 `cardia` 始终排第一；`org.eclipsehealth.cardia` 模块被显式排除，避免与内置引擎重复。可用性 = 模块启用 + 每个 `files[]` 存在且 sha256 匹配 + 至少一个 `.onnx`；不可用给出中文 reason（缺失/校验失败/路径越界/未声明文件）。sha256 校验按 `(路径, mtime, size, 期望值)` 缓存，目录请求不重复哈希大模型。
- `analysis_service/onnx_engine.py`（新建）：`OnnxEngineRunner` 用 `onnxruntime.InferenceSession`（CPU，`EH_ONNX_INTRA_THREADS`/`EH_ONNX_INTER_THREADS`，默认 1/1）加载单文件 ONNX；会话按 sha256 缓存；加载前后都校验 sha256。
- `analysis_service/service.py`：`submit` 从 descriptor 写 `moduleId/modelId/modelVersion`；`run_once` 按分析行的 `engine` 分派，Cardia 路径零改动；`OnnxEngineError` 落库为 `status=failed` + `error.code=engine_error`。模块引擎不触发 Cardia 预热。
- 测试：`backend/tests/analysis_service/test_onnx_engine.py`（13 例）、`fixtures/onnx/mul_1.onnx`、`fixtures/modules/onnx/{module.json,src/main.py}`；`conftest.py` 增加打包/安装/注入夹具。

## preprocess / output 支持范围
- `preprocess`：`lead`（只做导联一致性警告，单导联无法换导联）、`samplingRate`（回退 `fs`/`input.fs`，用现有 `resample_signal` 重采样）、`windowSamples`（可回退 `input.windowSamples` 或模型静态末维）、`strideSamples`（默认=窗口）、`normalize` = `none|zscore|minmax`（逐窗口）、`channels`（>1 时复制单导联；rank-3 静态中间维可推断）。未声明的字段只记录、不执行。
- `output`：仅 `{"type":"classification","classes":[...],"aggregation":"mean|max"}`。输出按 `(n,C)` 解释；probabilities 直接使用，否则按行 softmax；`max` 聚合后重新归一化。形状/类型不符、多维输出、非数值输出 → `engine_error`。
- 输入：支持 rank-2 `(B,F)` 与 rank-3 `(B,C,W)` / `(B,W,C)`；静态 batch 自动切块并零填充尾块，动态 batch 一次前向。仅单输入、单输出、单文件 ONNX。

## 验证
- 命令：`backend\.venv\Scripts\python.exe -m ruff check backend`
- 结果：`All checks passed!`
- 命令：`backend\.venv\Scripts\python.exe -m pytest backend\tests\analysis_service backend\tests\analysis -q`
- 结果：`103 passed in 214.28s`（含真实 Cardia ONNX 慢测与新增 13 例；新用例单独运行 13 passed）。
- 覆盖：目录列出/禁用消失/文件缺失/校验失败；runner 正常分类、确定性、形状不匹配、非法输出类型、短信号 pad/drop；API 选模块引擎落库（engine/moduleId/modelId/modelVersion、0 逐搏、2 条测量、非诊断警告、provenance sha256）、未知引擎 422、不可用引擎 `engine_unavailable`。

## 未验证 / 限制
- 只用 onnxruntime 自带 `mul_1.onnx`（rank-2 静态 `[3,2]`）验证；未验证真实第三方 ECG 模型、rank-3 输入、多导联、动态 batch、外部权重文件（external data 不支持）、safetensors/remote。
- `quality` 置空（不自造信号质量分）；`beats` 为空；测量值是模型输出的类别概率（百分比），不是核心测量码。

## 未做 / 偏离
- 未改 `api/analyses.py`、`schemas/module.schema.json`、`modules/manager.py`、前端；未新增依赖；未 commit。
- 偏离：prompt 说“复制到 fixtures/onnx/”，实际提交了 130 字节的 `mul_1.onnx` 副本（来自 onnxruntime 1.31.1，MIT），测试不再运行时写仓库。
- 模块引擎只出现在 `GET /analyses/engines`；`GET /engine` 仍是 Cardia 预热状态。

## 跨区需求（需要别的 Agent 或指挥官处理）
- UI 选中模块引擎时，若 `available=false` 应展示 reason 并禁用提交（API 仍会 202 后异步失败为 `engine_unavailable`）。

## 需要指挥官决策
- 是否把模块引擎的就绪/执行信息并入 `GET /engine`，或新增独立状态接口。

## 建议下一批
- 支持真实 ONNX 分类模型的端到端样本与 rank-3/多导联契约；为模块引擎补模型卡展示与 `available` 前置校验。

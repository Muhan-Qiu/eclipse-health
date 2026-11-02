# A3 · 平台 #1：通用 ONNX 分析引擎 loader（第二引擎）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V1.md` 的 `analysis-model` 与 `models` 段，再读本文件。

## 目标

让**已安装的 analysis-model 模块**能把自带 ONNX 模型注册成分析引擎，出现在 `GET /api/v1/analyses/engines`，并可被 `POST /records/{id}/analyses` 选中执行。Cardia 仍是默认引擎；不要伪造一个生产用第二引擎。

## 交付

### 1. 引擎目录扩展

- 修改 `backend/src/eclipse_health_backend/analysis_service/engines.py`：
  - 保留内置 `cardia`；
  - 扫描已安装且 enabled 的 `analysis-model` 模块，读取 `contributes.models[]`（`format="onnx"`、`files[]`、`input/output/preprocess/modelCard`），生成 `EngineDescriptor`：
    - `id = "<moduleId>:<modelId>"`（避免与内置冲突）；
    - `available`：模块 enabled + 模型文件存在 + sha256 校验通过；
    - `reason`：不可用时给出用户可读原因（模块未启用/文件缺失/校验失败）。
  - `get_engine(id)` 同时支持内置与模块引擎；未知仍返回 None。
- 不修改 `api/analyses.py`（它已通过 `list_engines()` 校验）；如需补字段只加 descriptor，不改 API 形状。

### 2. ONNX 执行器

- 新建 `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py`：
  - 用 `onnxruntime.InferenceSession` 加载模型（CPU，单线程可配置）。
  - 预处理按 manifest `preprocess` 的受控字段执行：`lead`（选导联，默认第一导联）、`samplingRate`（必要时用现有重采样）、`windowSamples/strideSamples`、`normalize`（`none|zscore|minmax`）、`channels`。
  - 输出按 manifest `output` 的受控类型映射：至少支持 `{"type":"classification","classes":["N","SVEB","VEB","F"],"aggregation":"mean|max"}`；生成合法的 `AnalysisResult`：
    - `engine/modelId/modelVersion` 正确；
    - `summary` 明确「模型级分类，非逐搏诊断」；
    - `beats` 可为空；`measurements` 只放模型确实输出的项；
    - `warnings` 含「非诊断」「模型由第三方提供」；
    - `provenance` 记录模型来源与 sha256。
  - 任何形状不匹配 → 明确 `engine_error`，不要静默返回空结果。
- `analysis_service/service.py`：`run_once` 按 analysis 行的 `engine` 分派到 Cardia bridge 或 ONNX runner；Cardia 行为保持不变。

### 3. 测试

- `backend/tests/analysis_service/test_onnx_engine.py`（新建）：
  - 用 `onnxruntime/datasets/mul_1.onnx` 或 `sigmoid.onnx` 复制到 `backend/tests/fixtures/onnx/`，验证 runner 能加载、预处理、执行、映射输出（可用一个测试用 manifest 描述该模型）；
  - 模型文件缺失/校验失败 → `available=false` + reason；
  - 模块 disabled → 不出现在目录；
  - 通过 API 选模块引擎发起分析，analysis 行 `engine/modelId` 正确（可 mock 后台执行或直接调 runner）；
  - Cardia 现有测试全绿。
- 不要提交大型模型；fixture 只用 onnxruntime 自带小模型。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/analysis_service/engines.py`
- `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py`（新建）
- `backend/src/eclipse_health_backend/analysis_service/service.py`
- `backend/tests/analysis_service/**`
- `backend/tests/fixtures/onnx/**`（新建）
- `backend/tests/fixtures/modules/onnx/**`（只加本任务的测试用 analysis-model manifest）

## 明确不做

- 不改 `schemas/module.schema.json`（A1 所有权）、不改 `modules/manager.py`（A2 所有权）、不改前端（widget/引擎 UI 已可用）。
- 不做模型下载、远程模型、GPU、per-module venv。
- 不新增依赖（onnxruntime 已装）；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\analysis_service backend\tests\analysis -q
```

报告 `reports/A3-onnx-engine-report.md`，≤80 行。必须写清：模块引擎 id 规则、preprocess/output 支持范围、真实测试输出、未验证的模型形状、未做项。

# B1-03 · Cardia 分析引擎

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B1 地基
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标不是「重新实现一遍」，而是把已有 Cardia 2.0 推理链**干净地移植成库**，并用数值对齐证明没搬坏。

## 1. 必读 / 必看

- `docs/DATA_SCHEMA_V1.md`：§6 AnalysisResult、§7 Measurement、§8 Beat/Quality、§12 限制。
- `docs/V3_FEATURE_BACKLOG.md`：C1–C7（分析结果要能支撑这些 UI）。
- 参考实现（**只读**）：
  - `..\V2\发布预权重与评分信息\推理代码\inference.py`
  - `..\V2\发布预权重与评分信息\推理代码\feature_extract.py`
  - `..\v1\feature_extract.py`、`..\v1\ecg_tools.py`（Ingest / R 峰 / 质量参考）
- 资源：
  - `backend/resources/models/cardia/cardia_k4_best.onnx`
  - `backend/resources/models/cardia/model_config.json`
  - `backend/resources/models/cardia/preprocess.json`
  - `backend/resources/samples/{100,200,208}.{hea,dat,atr}`

## 2. 目标

产出**纯 Python 库**：输入一条 ECG（WFDB / CSV / ndarray），输出符合 Schema 的 `AnalysisResult`（dict 或 Pydantic），不依赖 FastAPI、数据库、模块系统。B1 不做前端、不做数据库写入、不包成模块。

## 3. 你必须交付

1. **特征与推理（数值必须对齐）**
   - 移植 `extract_104(mlii, anns)`：104 维特征、`pre_r`、labels；保留原算法的边界处理。
   - ONNX 推理：从字节加载（Windows 中文路径），输入 `x [1,64,104]`、`dt [1,64]`；softmax；`sequence_length=64`、`stride=64`；类别顺序从 `preprocess.json` / `model_config.json` 读取（N/SVEB/VEB/F）。
   - 写一个**对齐测试**：同一记录、同一 R 峰，和 `..\V2\...\inference.py` 的 `predict_record` 输出逐 beat 概率比较，最大绝对误差 < 1e-4；在报告中给出实测值。
2. **Ingest**
   - WFDB：读取多导联，优先 `MLII`，否则第一导联；物理单位 mV；采样率不是 360Hz 时重采样到 360Hz（记录原采样率与是否重采样）。
   - CSV / NPY：单导联数值数组 + 采样率 + 单位；自动/显式指定列。
   - 统一返回 `EcgSignal`：`samples`（float32, mV）、`fs`、`lead`、`durationSec`、`source`。
3. **R 峰**
   - 有 `.atr` 标注时用标注（`rpeakSource="annotation"`），用于对齐与测试。
   - 无标注时用 `neurokit2.ecg_peaks`（method="neurokit" 或 pantompkins）检测，失败再退 scipy；返回样本索引；标记 `rpeakSource="detected"`。
4. **质量与测量**
   - 质量：幅度范围、平线、削顶、高频噪声、RR 异常比例 → `score 0–1`、`level`、`warnings`；不要宣称临床级。
   - 测量：`heart_rate_mean/min/max`、`rr_mean`、`sdnn`、`rmssd`、`pnn50`、`n_ratio`、`svb_ratio`、`veb_ratio`、`f_ratio`；按 §7 结构输出。
   - QRS/PR/QT/QTc：B1 可返回 `null` 并在 `warnings` 说明「未做波形 delineation」；如果实现，必须标注方法且不阻塞主流程。
5. **结果组装**
   - `analyze(signal, options) -> AnalysisResult`，字段按 §6：`schema/id/recordId/moduleId/modelId/modelVersion/task/status/startedAt/completedAt/durationMs/summary/quality/measurements/beats/warnings/parameters/provenance`。
   - `recordId` 由调用方传入（可为 `rec_...` 或临时 ID）；`id` 用 `ana_<UUIDv7>`，可复用 B1-01 的工具但**不要 import 后端 db/api**；自己实现小工具或接受注入。
   - beats：`index/rPeakSample/label/confidence/rrPrevMs`；超过 50,000 条不内联，返回 `beatsRef` 或截断并警告（二选一，报告说明）。
   - `summary` 一句话：类比例 + 平均心率；`parameters.engine="cardia"`、`sequenceLength=64`；`provenance` 记录模型/预处理版本与文件哈希。
6. **CLI**
   - `python -m eclipse_health_backend.analysis.cli --record backend/resources/samples/100 --format wfdb --out reports/analysis-100.json`
   - 也支持 `--csv <path> --fs 500 --lead I`。
   - 输出 JSON（UTF-8），stdout 只打印摘要。
7. **测试**
   - 3 个样本都能跑；beat 数与 `.atr` 的 R 峰数误差 ≤2%；概率每行和 ≈1；同输入两次结果一致。
   - 与 V2 推理的概率对齐测试（见上）。
   - 非法输入：空数组、采样率 ≤0、过短（<64 beat）、NaN/Inf、单值常量 → 明确异常。
   - 一个短记录与一个非 360Hz 重采样用例。
8. **性能**
   - 650k 样本单条记录的耗时与峰值内存，写进报告。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/analysis/**
backend/tests/analysis/**
backend/tests/fixtures/analysis/**      # 小型合成夹具；不要复制大样本
```

不要动：`app.py`、`settings.py`、`db/`、`api/`、`storage/`、`modules/`、`domain/`、`schemas/`、`src/`、`docs/`、`prompts/`、`uploads/`、`backend/pyproject.toml`。

依赖已装齐（numpy/scipy/wfdb/neurokit2/onnxruntime/pywavelets）。需要新依赖就写报告，不要安装。

## 5. 与后续批次的接口

- 你的 `analyze()` 必须能被 B2 的 `analysis-model` 模块直接调用：输入普通 Python 对象/dict，输出可 JSON 序列化的 dict；不要依赖 FastAPI 的请求模型。
- 不要 import `eclipse_health_backend.modules` 或 `db`；保持纯函数式、可单测。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend\src\eclipse_health_backend\analysis backend\tests\analysis
backend\.venv\Scripts\python.exe -m pytest backend\tests\analysis -q
backend\.venv\Scripts\python.exe -m eclipse_health_backend.analysis.cli --record backend/resources/samples/100 --format wfdb --out reports\analysis-100.json
```

报告写：3 个样本的 beat 数/耗时、对齐最大误差、未实现项（尤其 delineation）、CLI 输出位置。

## 7. 明确不做

FastAPI、数据库、模块安装、前端/UI、LLM、PDF、设备格式（Samsung/Apple/华为/SCP-ECG）、12 导联分析、模型训练/量化。只做单导联 Cardia 2.0 推理链。

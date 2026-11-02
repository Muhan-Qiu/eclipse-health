# 报告 · B1-03 Cardia 分析引擎
状态：完成

## 交付
- `backend/src/eclipse_health_backend/analysis/`：纯 Python 库，不依赖 FastAPI / 数据库 / 模块系统。
  - `engine.analyze(signal, options)`：质量 → 104 维特征 → ONNX 逐搏分类 → 测量 → AnalysisResult dict。
  - `ingest`：WFDB（优先 MLII，mV + 数字量）、CSV、NPY、ndarray；非 360Hz 自动重采样并记录 originalFs。
  - `features.extract_104`：移植 V2 特征管线（含 ±20 局部 R 峰、±90 窗、双中值滤波、AAMI 映射）；LBP/HOS 批量化、RR 预分配，数值与 V2 逐位一致。
  - `model.CardiaModel`：ONNX 从字节加载（兼容中文路径），输入 `x[1,64,104]`/`dt[1,64]`，softmax、64 搏非重叠切块、尾部补窗；会话按文件哈希进程级缓存。
  - `quality`、`measurements`、`ids`（UUIDv7）、`cli`。
- 测试 `backend/tests/analysis/` 共 51 项；CLI 输出 `reports/analysis-100.json`。

## 验证
- `ruff check backend\src\eclipse_health_backend\analysis backend\tests\analysis` → All checks passed。
- `pytest backend\tests\analysis` → **51 passed in 199.91s**（其中 ONNX 会话初始化约 150s）。
- 与 V2 `predict_record` 逐搏对齐（同一记录、同一标注、同一 ONNX 会话）：
  - 100：2271 搏，特征最大误差 8.9e-16，概率最大误差 **6.2e-7**，analyze 0.76s
  - 200：2600 搏，8.9e-16 / **7.0e-7**，1.03s
  - 208：2951 搏，8.9e-16 / **6.5e-7**，1.17s
  - 阈值 1e-4；概率行和 1.0。
- beat 数 vs `.atr` AAMI R 峰：2271/2273、2600/2601、2951/2953（均 ≤0.1%，门槛 2%）。
- 性能（650k 样本，record 100）：读信号 0.52s，特征 0.66s，推理 0.10s，`analyze` 0.82s；ONNX 会话初始化 146.6s。
  内存：RSS 272.5→302.4 MB，进程峰值 321.4 MB，tracemalloc 峰值 29.8 MB。
- CLI 端到端 2m42s（其中 ONNX 初始化约 160s），JSON 624KB、UTF-8；stdout 只打印摘要。
- 非法输入：空数组、fs≤0、NaN/Inf、常量、<64 搏、无 R 峰 → 明确异常。
- 确定性：固定 id/clock 两次 analyze，beats / measurements / quality 完全一致。
- 非 360Hz：500Hz CSV 重采样到 360，`originalFs=500`、`resampled=true`，短记录零填充路径通过。

## 未做 / 偏离
- 未做波形 delineation：QRS/PR/QT/QTc 以 `value=null` + warnings 返回。
- beats 超过 50,000：选择「截断 + 警告」（未实现 beatsRef 文件）；测量值仍基于全部心搏。
- `measurements` 返回完整 Measurement 对象（带 `msr_` ID），不是 §6 示例中的 ID 数组；B1 无数据库，B2 可直接消费。
- 每个 beat 额外带 `probabilities`（§8.2 未定义），支撑 C2「点选单搏看概率」。
- 类别比例与 pNN50 用百分数 0–100（unit=`%`）。
- 短记录默认抛异常（按提示词要求）；30s 手表记录需显式 `allow_short_record=True`。
- ONNX 会话初始化本机 146–165s，与优化级别无关；推理仅 0.1s，已做进程级缓存。
- `compute_rr_intervals` 的 global_R 保留参考算法的 O(n²)；2k 搏无感，24h 记录需优化。
- 未做 12 导联、设备格式、数据库、FastAPI、模块打包（按范围）。

## 跨区需求
- B2 `analysis-model`：直接调用 `analyze(EcgSignal|dict, AnalysisOptions|dict)`；sidecar 常驻以复用 ONNX 会话。
- B1-01 入库：`measurements` 已是完整对象，取 `id` 即可；beats 目前无独立 ID。
- 文档（指挥官）：§6 measurements 的 ID 数组 vs 库输出对象；§8.2 Beat 增加 `probabilities`；§12 beatsRef 策略需确认。
- UI（B1-04）：warning 用 `code` 做 i18n，`message` 仅兜底；`quality.level` 可直接映射颜色。

## 需要指挥官决策
- 短记录默认策略：保持「抛异常 + 显式 opt-in」，还是对 ≤64 搏的手表记录默认零填充。
- beats > 50k 用截断还是写 `beatsRef` 文件。
- measurements 是否改为「ID 数组 + 单独列表」。

## 建议下一批
- B2 把 analysis 包成 `analysis-model` 模块，并预热 ONNX。
- 波形 delineation（QRS/PR/QT/QTc）单列后续批次。
- 长记录：global_R 滑动窗口、beatsRef 文件、分段质量 segments。
- 评估 onnxruntime 优化模型缓存/模型简化以降低初始化时间（需验证数值影响）。

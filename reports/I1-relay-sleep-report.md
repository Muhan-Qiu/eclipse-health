# 报告 · I1 Relay 睡眠模型包（3 个自研 + 2 个更低基线）
状态：完成（含 1 处已记录的输入契约偏离）

## 交付
- `modules/official/relay-sleep/`：manifest、README/NOTICE、`src/main.py`（stdio JSON-RPC：initialize/warmup/health/list_models/predict/stats/deactivate）、`src/adapter.py`（形状校验、softmax、摘要）、`models/index.json`、`models/verify.json`。
- 5 个 ONNX 在 `uploads/relay-sleep/models/`（gitignore，不入库）：3 个 Relay/BiLSTM + Chambon2018 + AttnSleep。
- `tools/export_models.py`：从用户实验目录重导 ONNX，opset 17、dynamic batch，并写 verify/index。
- `backend/tests/modules/test_official_relay_sleep.py`：7 个测试。
- `scripts/pack_official_modules.py`：relay-sleep 打包时从 uploads 暂存权重；`.gitignore` 增加 ONNX 规则。

## 验证
- 导出/一致性（anaconda Python 3.x + torch 2.5.1，onnxruntime 1.27）：5/5 模型 PyTorch vs ORT argmax 一致率 **1.0000**；maxAbsDiff ≤ 5.7e-6；动态 batch 另测 B=3/B=2 通过。
  - Relay 输入 `features [B,10,272]`、`dt [B,10,1]` -> `logits [B,10,5]`；基线输入 `windows [B,3,C,3000]` -> `logits [B,5]`。
  - 文件 9.4MB / 9.4MB / 25MB / 36KB / 2.2MB，合计 46MB；`.ehmod` 42MB，低于单文件 64MB 与解压 256MB 上限。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_relay_sleep.py -q`：**7 passed，约 5.0s**（含真实权重 predict 两族）。
- `ruff check modules/official/relay-sleep backend/tests/modules/test_official_relay_sleep.py scripts/pack_official_modules.py`：**All checks passed**。
- 验收命令 `ruff check backend modules/official scripts`：**失败，仅因跨区 `modules/official/relay-ecg` 13 条**（UP035/RUF046/I001/F401/RUF100/TRY203），本任务未改动该目录；排除 relay-ecg 后全仓通过。
- `scripts/pack_official_modules.py`：31 模块打包成功，产出 `dist/modules/org.eclipsehealth.relay-sleep-0.1.0.ehmod`，解压校验 checksums/layout 通过。
- 端到端：解压 ehmod 后 warmup/list_models/predict（relay + baseline）/非法形状/health/deactivate 全部符合预期；空数据 stats 返回 `hasData:false`。

## 未做 / 偏离
- **基线输入偏离任务提示**：Chambon2018/AttnSleep checkpoint 是 30s 原始 EEG 端到端模型（head 为 272/2400 维前端特征 × 3 窗，输入 `[B,3,C,3000]`），无法接受 272 维冻结特征；强行统一会造出无意义模型。故按真实架构导出并在 index/module.json/README 标注 `inputKind:"raw-windows"`。3 个自研模型严格满足 `[B,10,272]+dt -> [B,10,5]`。
- 分数采用 checkpoint 实测：Chambon2018 seed4 的 history 最高 valid BA **0.7695**、AttnSleep seed1 **0.7499**；任务提示的 0.7883 / 0.757–0.765 与这两个文件不符（疑似 seed0/其它 tag），自研仍为 0.8139/0.8118/0.8083，排序满足 ours > baseline。
- AttnSleep seed1 在原始实验中为 PAUSED（第 11 轮），权重与分数如实使用；未重训。
- 不做 EDF 解码与 mne 特征提取；未接主界面；未新增核心依赖（基线架构按用户机器上的 braindecode 1.8.1 源码导入，不安装）。
- 未提交 git；未改用户原始代码/数据。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `modules/official/relay-ecg/` 当前 13 条 ruff 错误，导致全量验收命令失败；请 relay-ecg 所有者修复。
- `backend/src/eclipse_health_backend/marketplace/config.py` 处于别的 Agent 修改中，未触碰。

## 需要指挥官决策
- 是否接受两个基线以 `windows` 原始窗输入（而非统一 272 维特征）。若必须统一，只能新增/训练特征头或改选特征基线，超出本任务。
- 确认基线展示分数使用实测 0.7695/0.7499，还是要求前端目录展示任务提示的 0.7883/0.757–0.765。

## 建议下一批
- 睡眠 EDF/PSG 导入 + 272 维特征提取（mne），打通端到端流程。
- 模块页接入真实记录（当前 stats 为空），并在 UI 展示模型选择与分数对照。
- 基线如需特征口径，可另训 Chambon 特征上的轻量头并重新导出。

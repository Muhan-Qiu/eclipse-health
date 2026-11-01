# ECG 心搏分析 · 多模型心搏分类

`org.eclipsehealth.relay-ecg` 把一段 ECG 自动切成心搏并分为 N / SVEB / VEB / F，内置 7 个可切换的分类模型
（4 个自研 Relay-LSTM + 3 个基线），适合科研复现、教学与算法对照。模块 ID 保持不变。

**非医疗器械，不用于诊断。** 所有输出都带 `nonDiagnostic` 字段，只用于科研、教学与模型对比。

## 模型与分数

| id | 类别 | 4 类 macro F1 | checkpoint |
|---|---|---|---|
| relay-k2 | ours | 0.5706 | `relay_k2_s0.pt` |
| relay-k12 | ours | 0.5417 | `relay_k12_s0.pt` |
| relay-k4 | ours | 0.5397 | `relay_k4.pt` |
| relay-k8 | ours | 0.5199 | `relay_k8.pt` |
| bilstm | baseline | 0.4186 | `bilstm.pt` |
| resnet1d | baseline | 0.4178 | `resnet1d.pt` |
| tlstm | baseline | 0.3522 | `tlstm.pt` |

分数口径：DS1 训 / DS2 测、AAMI 4 类（N/SVEB/VEB/F）macro F1、5 种子均值，来源
`relay LSTM/10月19日WFDB基线测试/results_features/总表.md`。这是**精选子集**，不是 V1
全量排行榜：V1 的 `lstm` 等基线在部分口径下高于 `relay_k4/k8`，按本包要求未收录。
ONNX 权重来自 V1 raw-window checkpoint（`V1/results/ckpt/`，5 类含 Q）；分数表来自
特征标尺实验，两者不是同一次评测，模型卡与索引如实标注，不把分数当作临床性能。

## 输入协议（复刻 V1 `train_mitbih.py`）

- 360 Hz、两导联（MIT-BIH 的 MLII + 第二导联）；单导联输入会复制成两路并在 `leads` 中标明。
- R 峰前 90 采样点、后 144 采样点，窗口 234 点；逐导联 z-score。
- 序列模型每条 64 个连续心搏，末尾不足 64 的丢弃；`dt = RR 秒 / (275/360)`。
- 采样率不是 360 Hz 直接报 `sampling_rate_mismatch`，不静默重采样。

## API（stdio JSON-RPC 2.0）

`initialize` / `warmup` / `health` / `list_models` / `analyze` / `stats` / `deactivate`

`analyze` 参数：

```json
{
  "modelId": "relay-k2",
  "wfdbPath": "C:/data/mitdb/100",
  "leads": ["MLII", "V5"],
  "options": { "maxSeconds": 120, "includeBeats": false }
}
```

也接受 `signalRef`（float32 文件 + `fs` + 可选 `sha256`）或内联 `samples`（`[N]` 或
`[N, C]`）。有 `.atr` 时用 AAMI 标注定位 R 峰，否则用 `wfdb.processing.xqrs_detect`。
返回均值概率、argmax 计数、逐序列摘要与 `summaryText`。

## 权重与打包

ONNX 不提交 git：导出到 `uploads/relay-ecg/models/`，索引在
`modules/official/relay-ecg/models/index.json`（含 sha256）。`scripts/pack_official_modules.py`
在打包时把权重复制进 staging，产出
`dist/modules/org.eclipsehealth.relay-ecg-0.1.0.ehmod`。

重新导出（需 torch 2.5.1 + onnx + onnxruntime）：

```powershell
C:\Users\qiumuhan\anaconda3\python.exe modules\official\relay-ecg\tools\export_onnx.py
```

导出脚本对每个模型做 PyTorch/onnxruntime argmax 一致率校验（阈值 ≥99%，实测 100%）。

## 边界与错误

- `model_not_found`（404）：`modelId` 不在索引里；
- `model_missing`（503）：ONNX 未安装；
- `too_few_beats`（422）：不足 64 个有效心搏；
- `sampling_rate_mismatch`（422）：不是 360 Hz；
- `invalid_lead` / `invalid_signal` / `beat_detection_failed`：输入或 R 峰检测失败。

## 许可

模块适配代码：GPL-3.0-only（与核心一致）。训练数据：MIT-BIH Arrhythmia Database
（PhysioNet），使用时遵循其数据许可。详见 `NOTICE`。

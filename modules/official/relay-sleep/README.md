# 睡眠分期分析

`org.eclipsehealth.relay-sleep` 把整夜睡眠逐窗分成 W / N1 / N2 / N3 / REM，并汇总各阶段时长、
占比与睡眠结构。内置 5 个可切换的分期模型；模块 ID 保持不变。

## 模型

| id | 类别 | 输入 | 输出 | 参考 BA |
|---|---|---|---|---|
| `paper-highway-h-k2-c256` | 自研 Relay | features `[B,10,272]` + dt `[B,10,1]` | logits `[B,10,5]` | 0.8139 |
| `paper-highway-h-k2-b256` | 自研 Relay | 同上 | 同上 | 0.8118 |
| `bilstm-l4-b256` | 自研 BiLSTM | 同上 | 同上 | 0.8083 |
| `chambon2018-seed4` | 基线 | windows `[B,3,2,3000]` | logits `[B,5]` | 0.7695 |
| `attnsleep-seed1` | 基线 | windows `[B,3,1,3000]` | logits `[B,5]` | 0.7499 |

- 自研模型使用冻结的 272 维 Chambon 特征，序列长度固定 10；输出为逐窗 logits。
- 两个基线是 30 秒原始 EEG 的端到端模型（3 个连续窗 -> 中间窗序列标签），
  其 head 使用自身前端特征，**不能**接受 272 维冻结特征，因此单独声明 `windows` 输入。
- 分数为 `balanced_accuracy`；基线必须低于自研最低分。详见 `models/index.json` 与
  `models/verify.json`（导出形状、参数量、PyTorch/onnxruntime 一致率、sha256）。

## RPC 方法

`initialize` / `warmup` / `health` / `list_models` / `predict` / `stats` / `deactivate`。

```json
{"jsonrpc":"2.0","id":1,"method":"predict","params":{
  "modelId":"paper-highway-h-k2-c256",
  "features":[[0.1,0.2,"... 272 维 ..."]]
}}
```

`features` 可以是嵌套数组或 `.npz` 路径（`features` 或 `X`，可选 `dt`）；
基线模型用 `windows`（嵌套数组或 npz 里的 `windows`/`X`）。返回逐单元 logits、
argmax 与 `summary`（计数、占比、多数类）。权重缺失时返回
`{"error":{"code":"model_unavailable"}}`，不影响其它方法。

## 权重与导出

权重不提交 git。把 5 个 `.onnx` 放到 `uploads/relay-sleep/models/`，打包脚本会自动
复制进 `.ehmod`。重新导出（需要用户的原始实验目录与 torch 2.5.1）：

```powershell
C:\Users\qiumuhan\anaconda3\python.exe modules\official\relay-sleep\tools\export_models.py
```

## 限制

- 只接收已缓存特征或原始窗，不做 EDF 解码与特征提取。
- 训练/验证均来自 Sleep-EDF sleep-cassette；跨数据集、跨设备泛化未验证。
- 所有输出仅供研究与教育用途。

# Cardia 2.0 · ECG 心搏分类模块

官方 `analysis-model` 模块。把一个导联的 ECG 波形分成 N / SVEB / VEB / F 四类心搏，
并给出质量、心率与间期测量。属于**研究/教育用途**，不构成医疗诊断。

## 模型卡

| 项 | 值 |
|---|---|
| 模型 ID / 版本 | `cardia-2.0` / `2.0.0` |
| 任务 | 逐搏心律失常分类（4 类） |
| 参数量 | ≈722k（ONNX 初始化器 float32 元素数；导出按窗口展开会重复常量） |
| 输入 | 单导联（MLII），360 Hz，104 维特征，窗口 64 搏，非重叠 + 尾部左移补齐 |
| 输出 | `N` / `SVEB` / `VEB` / `F` 逐搏概率 |
| 预处理 | `mondejar-104-v1`（与 V2 特征管线逐位一致） |
| 训练数据 | MIT-BIH Arrhythmia（MLII） |
| 评测 | 与 V2 `predict_record` 逐搏对齐：概率最大误差 6.2e-7；合成指标 74.0 |
| 局限 | 仅单导联 MLII、仅 360 Hz、无波形 delineation（QRS/PR/QT 不可用） |
| 许可证 | GPL-3.0-only |

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手；返回能力与模型摘要。要求 `apiVersion` 主版本为 1 |
| `warmup` | 触发后台预热（ONNX 会话初始化），立即返回当前健康状态 |
| `health` | `{ok, warm, warmupSeconds, error}`；`warm=true` 才可分析 |
| `analyze` | 见下；成功返回 AnalysisResult，业务失败返回 `{error:{code,message}}` |
| `deactivate` | 退出 |

### `analyze` 参数

```json
{
  "recordId": "rec_...",
  "analysisId": "ana_...",
  "signalRef": {
    "path": "C:/.../tmp/analyses/ana_.../ana_....f32",
    "sha256": "...",
    "fs": 360,
    "lead": "MLII",
    "unit": "mV",
    "nSamples": 650000
  },
  "options": { "allowShortRecord": false, "tailMode": "pad" }
}
```

- 波形只走临时 float32 文件句柄（小端、无头），按 `sha256` 校验；`nSamples` 不符即拒绝。
- 结果 JSON 超过 3.5MB 时写入临时文件，返回 `{"resultRef": {path, sha256, bytes}}`。
- 业务错误码：`too_few_beats`、`invalid_signal`、`model_load_failed`、`engine_warming`。

## 实现说明

本模块直接调用核心内置的 `eclipse_health_backend.analysis` 库（与核心共用同一个
后端解释器与虚拟环境）。B3 引入每模块 venv 后，应把分析库与 ONNX 权重作为模块
自己的依赖打包，届时只替换 `src/main.py` 的导入路径，RPC 契约不变。

## 打包

```powershell
backend\.venv\Scripts\python.exe scripts\pack_cardia.py
# -> dist/cardia-1.0.0.ehmod（含 checksums.json，脚本自校验）
```

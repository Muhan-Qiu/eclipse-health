# BioSPPy · ECG 模块

官方 `analysis-model` 模块，适配自 [scientisst/BioSPPy](https://github.com/scientisst/BioSPPy)（BSD-3-Clause）。
只暴露 ECG/HRV 子集：单导联 ECG R 峰检测、RR 间期与时域 HRV 指标。

> 非医疗器械，不用于诊断。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` / `health` | 健康状态与库版本 |
| `analyze` | 接受 `rr`（毫秒数组）或 `signalRef`（float32 临时文件 + fs） |
| `stats` | widget/pages 数据源；接受可选 `rr` |
| `ecg.quality` | 基于 RR 数量与范围的质量判断 |
| `deactivate` | 退出 |

## 适配说明

- 依赖：`biosppy`、`numpy`、`scipy`、`h5py`、`scikit-learn` 装入模块独立 venv。
- 与 NeuroKit2 功能重叠，本模块作为交叉校验/备选；EDA/EMG/呼吸信号不暴露。
- `rpeaks_to_rr` 为纯函数：样本索引 → 毫秒 RR，并有独立单测。
- 本适配层 GPL-3.0-only；上游 BSD-3 版权与许可说明见 `NOTICE`。

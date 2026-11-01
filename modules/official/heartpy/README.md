# HeartPy · PPG/ECG 模块

官方 `analysis-model` 模块，适配自 [paulvangentcom/heartrate_analysis_python](https://github.com/paulvangentcom/heartrate_analysis_python)（MIT）。
提供 PPG/ECG 心率、HRV 时域指标与信号质量标志。

> 非医疗器械，不用于诊断。低质量信号仍可能返回数值，必须结合 `quality` 字段解读。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` / `health` | 健康状态与库版本 |
| `analyze` | 接受 `rr`（毫秒数组）或 `signalRef`（float32 临时文件 + fs） |
| `stats` | widget/pages 数据源；接受可选 `rr` |
| `ppg.quality` | 质量评估；接受 `rr` 或 `accepted` |
| `deactivate` | 退出 |

## 适配说明

- 依赖：`heartpy>=1.2,<2` 装入模块独立 venv。候选表标为 E（numpy/scipy 已满足），但核心 venv
  未安装 `heartpy` 本身，故显式声明依赖（见报告「偏离」）。
- `hp.process` 的 `binary_quality_score` 映射为 `quality.label`（good/poor）。
- 波形只走临时 float32 文件句柄，按 sha256 校验；不写日志、不出本机。
- 本适配层 GPL-3.0-only；上游 MIT 版权与许可说明见 `NOTICE`。

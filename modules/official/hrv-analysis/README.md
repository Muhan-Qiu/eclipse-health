# hrv-analysis · HRV 模块

官方 `analysis-model` 模块，适配自 [Aura-healthcare/hrv-analysis](https://github.com/Aura-healthcare/hrv-analysis)（GPL-3.0）。
提供 RR 间期的时域指标与频域指标（VLF/LF/HF、LF/HF、归一化功率）。

> 非医疗器械，不用于诊断。频域结果依赖记录长度与平稳性，短记录不可靠。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` / `health` | 健康状态与库版本 |
| `analyze` | 接受 `rr`（毫秒数组），可选 `frequency`（默认 true） |
| `stats` | widget/pages 数据源；接受可选 `rr` |
| `hrv.frequency` | 工具方法，返回频域指标；上游缺失时返回 `dependency_missing` |
| `deactivate` | 退出 |

## 适配说明

- 依赖：`hrv-analysis`、`pandas`、`numpy`、`scipy`、`astropy`、`nolds` 装入模块独立 venv。
- 时域指标用纯 Python 计算，作为上游库缺失时的降级路径；频域必须走上游库。
- GPL 隔离：只经 stdio JSON-RPC 通信，不静态链入核心。
- 本适配层 GPL-3.0-only；上游 GPL-3.0 版权与许可说明见 `NOTICE`。

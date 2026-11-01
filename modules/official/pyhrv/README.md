# pyhrv · HRV 工具箱模块

官方 `analysis-model` 模块，适配自 [PGomes92/pyhrv](https://github.com/PGomes92/pyhrv)（BSD-3-Clause）。
提供 RR 间期的时域 HRV 指标（mean RR、SDNN、RMSSD、pNN50 等）。

> 非医疗器械，不用于诊断。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` / `health` | 健康状态与库版本 |
| `analyze` | 接受 `rr`（毫秒数组），返回纯 Python 时域指标与上游交叉校验结果 |
| `stats` | widget/pages 数据源；接受可选 `rr` |
| `hrv.metrics` | 工具方法，返回 pyhrv 时域指标；上游缺失时返回 `dependency_missing` |
| `deactivate` | 退出 |

## 适配说明

- 依赖：`pyhrv`、`biosppy`、`nolds`、`spectrum`、`numpy`、`scipy` 装入模块独立 venv。
- 时域指标始终用纯 Python 计算；上游可用时追加 `upstreamTime` 交叉校验，缺失时降级并在 `upstreamError` 说明。
- 本适配层 GPL-3.0-only；上游 BSD-3 版权与许可说明见 `NOTICE`。

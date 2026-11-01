# YASA · 睡眠分期模块

官方 `analysis-model` 模块，适配自 [raphaelvallat/yasa](https://github.com/raphaelvallat/yasa)（BSD-3-Clause）。
提供 PSG 睡眠分期（W/N1/N2/N3/R）与睡眠效率、分期时长统计。

> 非医疗器械，不用于诊断。单设备数据通常不足以做 PSG 分期，结果仅供参考。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` / `health` | 健康状态与库版本 |
| `analyze` | 接受 `stages`（已分期序列）或 `signals`（eeg/eog/emg 数组）+ `sf` |
| `stats` | widget/pages 数据源；接受可选 `stages` |
| `sleep.efficiency` | 工具方法，纯函数计算睡眠效率与分期计数 |
| `deactivate` | 退出 |

`analyze` 示例：

```json
{ "stages": ["W", "N1", "N2", "N2", "N3", "R", "W"] }
```

```json
{ "signals": { "eeg": [0.1, -0.2, 0.3], "eog": [0.0], "emg": [0.01] }, "sf": 100 }
```

## 适配说明

- 依赖：`yasa`、`mne`、`lightgbm`、`pooch`、`pandas`、`numpy` 装入模块独立 venv。
- 上游训练权重随包分发，不在本仓库重复分发；许可按上游条款。
- 分期标签统一大写，`REM` 归一为 `R`；未知标签拒绝。
- 本适配层 GPL-3.0-only；上游 BSD-3 版权与许可说明见 `NOTICE`。

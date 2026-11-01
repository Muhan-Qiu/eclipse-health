# NeuroKit2 · ECG/HRV 模块

官方 `analysis-model` 模块，适配自 [neuropsychology/NeuroKit](https://github.com/neuropsychology/NeuroKit)（MIT）。
提供单导联 ECG 峰值检测与 HRV 时域指标（mean RR、mean HR、SDNN、RMSSD、pNN50）。

> 非医疗器械，不用于诊断。结果仅供研究与个人参考。

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，要求 apiVersion 主版本为 1 |
| `warmup` | 空实现，返回健康状态 |
| `health` | 返回库版本与可用性 |
| `analyze` | 接受 `rr`（毫秒数组）或 `signalRef`（float32 临时文件 + fs），返回 HRV 结果 |
| `stats` | widget/pages 数据源；接受可选 `rr` |
| `hrv.summary` | 工具方法，等价于只算时域指标的 `analyze` |
| `deactivate` | 退出 |

`analyze` 参数示例：

```json
{ "rr": [800, 812, 795, 808] }
```

```json
{ "signalRef": { "path": "C:/tmp/x.f32", "sha256": "...", "fs": 360 } }
```

## 适配说明

- 依赖：复用核心 venv 已安装的 `neurokit2`（E 类），`dependencies` 为空。
- 波形只走临时 float32 文件句柄，按 sha256 校验；不写日志、不出本机。
- 上游库缺失时返回业务错误 `dependency_missing`，不崩溃。
- 本适配层 GPL-3.0-only；上游 MIT 许可与版权见 `LICENSES/neurokit2-upstream.txt` 与 `NOTICE`。

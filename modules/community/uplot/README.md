# uPlot · 轻量趋势图

官方 `dashboard-widget` 模块，能力上借鉴 [uPlot](https://github.com/leeoniya/uPlot) 的轻量时序图，
用核心受控的 `sparkline` / `table` 组件表达，**不打包、不加载上游 JS**。

**非医疗器械，不用于诊断。** 模块只做数值序列的校验、排序、去重与降采样。

## 上游与许可

- 上游：uPlot / MIT（仅作能力参考，未复制源码）
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 无第三方 Python 依赖；worker 使用标准库

## RPC 方法

| 方法 | 参数 | 返回 |
|---|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | — | 生命周期 |
| `trend` | `{points: [{t,v}...], unit?, maxPoints?}` | `{points, latest, min, max, mean, count, unit}` |
| `summary` | `{points, unit?}` | 统计摘要；空数组返回零值 |

`points` 也接受 `[t, v]` 二元组；非数字或结构错误返回 `INVALID_INPUT`。

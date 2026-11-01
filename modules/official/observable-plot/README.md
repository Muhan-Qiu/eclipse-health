# Observable Plot · 声明式图形

官方 `dashboard-widget` 模块，能力上借鉴 [Observable Plot](https://github.com/observablehq/plot)，
把趋势、直方图与分位数摘要映射到核心受控组件，**不打包、不加载上游 JS/D3**。

**非医疗器械，不用于诊断。** 本模块只做数值统计与分组，不做医学解释。

## 上游与许可

- 上游：Observable Plot / ISC（仅作能力参考，未复制源码）
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 无第三方 Python 依赖；worker 使用标准库

## RPC 方法

| 方法 | 参数 | 返回 |
|---|---|---|
| `plot.trend` | `{points, unit?}` | `{labels, values, latest, count}` |
| `plot.histogram` | `{values, bins?}`（1..32） | `{items:[{label,count}], count}` |
| `plot.summary` | `{values}` | `{count,min,max,mean,median,q1,q3}` |

空数组返回零值；非数字或非法 `bins` 返回 `INVALID_INPUT`。

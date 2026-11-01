# ECharts · 通用图表

官方 `dashboard-widget` 模块，能力上借鉴 [Apache ECharts](https://github.com/apache/echarts)，
用核心受控的 `sparkline` / `list` / `table` 表达折线、柱状与直方图，**不打包、不加载上游 JS**。

**非医疗器械，不用于诊断。** 输出是渲染器无关的声明式图表 spec。

## 上游与许可

- 上游：Apache ECharts / Apache-2.0（仅作能力参考，未复制源码）
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 无第三方 Python 依赖；worker 使用标准库

## RPC 方法

| 方法 | 参数 | 返回 |
|---|---|---|
| `chart.line` | `{points:[{x,value}...], label?, unit?, xLabel?}` | `{kind:"line", labels, series, latest}` |
| `chart.bar` | `{categories, values, label?, unit?}` | `{kind:"bar", labels, series}` |
| `chart.distribution` | `{values, bins?}`（1..32） | `{items:[{label,count}], count}` |
| `summary` | `{values}` | `{count,min,max,mean}` |

长度不一致、非数字、非法 `bins` 返回 `INVALID_INPUT`。H2 的 bar/line 类型落地后可直接消费 `kind`。

# Tremor · KPI 仪表盘

官方 `dashboard-widget` 模块，能力上借鉴 [Tremor](https://github.com/tremorlabs/tremor)，
用核心受控 `stat` / `list` / `table` 表达 KPI 数值、变化量与完成度，**不打包上游 React/构建链**。

**非医疗器械，不用于诊断。** `delta` 只是数值差，不代表健康结论。

## 上游与许可

- 上游：Tremor / Apache-2.0（仅作能力参考，未复制源码）
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 无第三方 Python 依赖；worker 使用标准库

## RPC 方法

| 方法 | 参数 | 返回 |
|---|---|---|
| `kpis` | `{metrics:[{id?,label,value,unit?,previous?,min?,max?}]}` | `{cards, headline, count}` |
| `summary` | `{values}` | `{count,min,max,mean}` |

`value` 缺失或非数字返回 `INVALID_INPUT`；空数组返回 `cards: []`、`headline: null`。
`progress` 仅当同时提供 `min`/`max` 且 `max > min` 时生成。

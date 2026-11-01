# Activity Calendar · 活动热力图

官方 `dashboard-widget` 模块，能力上借鉴
[react-activity-calendar](https://github.com/grubersjoe/react-activity-calendar)，
把每日活动计数映射为 0–4 级热力图数据与活跃天数/连续天数统计。
用核心受控 `stat` / `list` / `table` 渲染，**不打包上游 React**。

**非医疗器械，不用于诊断。** 计数只表示记录条数，不代表健康评分。

## 上游与许可

- 上游：react-activity-calendar / MIT（仅作能力参考，未复制源码）
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 无第三方 Python 依赖；worker 使用标准库

## RPC 方法

| 方法 | 参数 | 返回 |
|---|---|---|
| `heatmap` | `{counts:{YYYY-MM-DD:n}, days?, today?}` | `{days:[{date,count,level}], recent, activeDays, longestStreak, currentStreak}` |
| `summary` | 同上 | 仅统计字段 |

`days` 取值 1..3660（默认 365）；非法日期或负数计数返回 `INVALID_INPUT`。
`level`：0 为无记录，1–4 按当窗口最大计数等比分级。

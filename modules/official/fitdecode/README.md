# FIT Decoder · eclipse health 模块

官方 `device-adapter` 模块，适配自 [polyvertex/fitdecode](https://github.com/polyvertex/fitdecode)。
把 Garmin / ANT `.FIT` 活动文件解析为活动会话摘要（时间、距离、心率、速度、质量）。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，返回能力列表 |
| `warmup` / `health` | 无重初始化；`health` 报告 `fitdecode` 是否可用 |
| `summary` | `{path, maxRecords?}` → `{summary, record}` |
| `importFile` | 同上，并返回采样记录（最多 5000 条，`truncated` 标记） |
| `latestSummary` | 返回本进程最近一次导入摘要，供首页 widget 使用 |
| `deactivate` | 退出 |

## 适配说明

- 只经 stdio JSON-RPC 调用，不把上游源码复制进本仓库；
- `src/adapter.py` 是纯函数映射层，核心 venv 无 `fitdecode` 也能单测；
- 时区沿用文件内的 ISO 时间；缺失心率按覆盖率降级 `quality`；
- 私有 profile 字段不识别，未知字段忽略。

## 许可与署名

- 本适配层：GPL-3.0-only（见 `LICENSE`）；
- 上游：MIT，见 `NOTICE`；发布前需把上游 LICENSE 放入 `LICENSES/fitdecode-upstream.txt`。

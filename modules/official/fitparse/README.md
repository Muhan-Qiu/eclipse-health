# FIT Parser · eclipse health 模块

官方 `device-adapter` 模块，适配自 [dtcooper/python-fitparse](https://github.com/dtcooper/python-fitparse)。
解析 `.FIT` 的 record/lap，输出活动会话摘要。与 FIT Decoder（fitdecode）二选一即可。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` | 握手与依赖状态 |
| `summary` | `{path, maxRecords?}` → `{summary, record}`，record 含最多 64 个 lap |
| `importFile` | 同上并返回采样记录（≤5000，带 `truncated`） |
| `latestSummary` | 本进程最近一次导入摘要 |
| `deactivate` | 退出 |

## 适配说明

- 位置字段按 FIT 半圆转换为 WGS84 度数；已为度数的输入保持不变；
- 心率/速度越界按缺失处理，`quality` 由心率覆盖率决定；
- `src/adapter.py` 为纯函数，`fitparse` 只在业务方法内导入。

## 许可与署名

- 本适配层：GPL-3.0-only；上游 MIT，署名见 `NOTICE`；
- 上游 LICENSE 需在发布前放入 `LICENSES/fitparse-upstream.txt`（构建环境未联网取得）。

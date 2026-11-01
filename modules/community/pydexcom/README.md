# Dexcom CGM · eclipse health 模块

官方 `device-adapter` 模块，适配自 [gagebenne/pydexcom](https://github.com/gagebenne/pydexcom)。
通过 Dexcom Share 读取**用户本人**的 CGM 血糖读数，输出 mg/dL、趋势与时间范围内占比。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` | 握手；`health` 报告依赖与联网要求 |
| `readings` | `{username, password, region?: "us"|"eu", minutes?, maxCount?}` |
| `latestReading` | 本进程最近一次读数（widget 数据源） |
| `deactivate` | 退出 |

## 隐私与网络

- 只访问 `share2.dexcom.com` / `shareous1.dexcom.com`（`allowedHosts`）；
- 用户名/密码只存在于单次 RPC 参数中，不落盘、不写日志、不返回；
- 适配的是非官方 Share API，可能因上游变更或风控失效；
- CGM 结果低于/高于阈值只做计数与提示，不给出治疗建议。

## 适配说明

- `src/adapter.py` 纯函数处理 mg/dL ↔ mmol/L、趋势码、时间范围内占比；
- `pydexcom` 只在 `readings` 调用时导入；
- 离线回放 JSON 字段：`{value|mmol_l, trend|trend_direction, timestamp}`。

## 许可与署名

- 本适配层：GPL-3.0-only；上游 MIT，署名见 `NOTICE`；
- 上游 LICENSE 需在发布前放入 `LICENSES/pydexcom-upstream.txt`。

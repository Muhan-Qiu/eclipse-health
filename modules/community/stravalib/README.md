# Strava Sync · 运动数据导入

官方 `data-source` 模块，适配自 [stravalib](https://github.com/stravalib/stravalib)。
把用户本人的 Strava 活动规范化为本地活动记录，并按 ISO 周汇总距离、时长与平均心率。

**非医疗器械，不用于诊断。** 只处理用户本人数据；access token 逐次传入，不落盘、不写日志。

## 上游与许可

- 上游：stravalib / Apache-2.0
- 本适配层：GPL-3.0-only（见 `LICENSE`、`NOTICE`）
- 运行时依赖：`stravalib>=2.0,<3`，只装进本模块的独立 venv

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `activities.normalize` | `{activities: [...]}` → 规范化活动数组；非法输入返回 `INVALID_INPUT` |
| `activities.weekly` | `{activities: [...]}` → 周汇总 `{weeks, series, totals}` |
| `strava.fetch` | `{accessToken, limit}` → 经 stravalib 拉取后规范化；网络/鉴权失败返回 `UPSTREAM_ERROR` |

## 隐私

token 不写日志；活动内容只经 stdout 的 JSON-RPC 返回。模块不做遥测、不上传健康数据。

# Garmin Connect 导入

适配自 [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect)（MIT）。
本模块是**薄适配层**：不复制上游源码，`import garminconnect` 调用非官方 REST 客户端；
依赖装进模块独立 venv（B 类）。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `import.garmin` | 登录后拉取活动、睡眠、身体成分；`email` / `password` / `count` |
| `import.summary` | 最近一次导入的汇总（供面板/页面） |

## 风险与边界

- **非官方 API**：可能因 Garmin 风控/2FA/改版而失效；需要 `network` 权限与
  `allowedHosts`（`connect.garmin.com`、`sso.garmin.com`）。
- 凭据只传给上游进程，不写日志、不落盘；仅导入用户本人数据，受 Garmin ToS 约束。
- 离线场景可先下载 JSON，再由上层转换为 `activity.session` 等记录。

## 贡献点

- `sources`：`garmin-connect`；`importFormats`：`garmin-json`
- `recordTypes`：`activity.session`、`sleep.session`、`body.measurement`
- UI：`garmin-steps` 统计卡 + 活动表页面

## 权限与依赖

- 权限：`network`、`records:write`
- pip 依赖：`garminconnect>=0.2,<1`、`curl_cffi>=0.7,<1`

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_garminconnect.py -q
```

未安装 garminconnect 时，导入测试自动 skip；适配层与 manifest 测试仍会执行。

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。

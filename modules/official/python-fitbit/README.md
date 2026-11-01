# Fitbit Data Sync · io.github.orcasgit.fitbit

Fitbit Web API 数据源模块，适配自 <https://github.com/orcasgit/python-fitbit>。
用于把用户本人的 Fitbit 活动、睡眠、心率和体重数据导入 eclipse health。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `auth.url`：生成 Fitbit OAuth2 授权地址（纯函数）。
- `auth.exchange`：用授权码换取 token（需要 `network` 权限）。
- `fetch`：从 Fitbit Web API 拉取 `activity` / `sleep` / `body` / `heartRate`（需要 `network` 权限）。
- `import`：解析调用方提供的 Fitbit JSON（离线，不发网络请求）。
- `stats` / `activity.list` / `sleep.list` / `body.list`：声明式 UI 页面/组件数据。

## 依赖

`fitbit`、`requests`、`requests-oauthlib`，只装进本模块独立 venv，不进入核心环境。
缺少依赖时 `health` 返回 `dependency.available=false`，网络方法返回
`MODULE_DEPENDENCY_MISSING`；`import` 与纯解析仍可用。

## 隐私与边界

- token 由核心/用户提供，模块不落盘、不写日志；健康数据默认不出本机。
- 仅导入用户本人账户数据；不是官方 Fitbit 应用。
- 所有输出附「非医疗器械，不用于诊断」。

## 许可

适配层 GPL-3.0-only；上游 Apache-2.0，见 `NOTICE` 与 `LICENSES/`。

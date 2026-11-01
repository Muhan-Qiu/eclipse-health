# Withings Body Measurements · io.github.vangorra.withings

Withings 身体测量数据源，适配自 <https://github.com/vangorra/python_withings_api>。
把用户本人的体重、体成分与血压测量导入 eclipse health。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `auth.url`：生成 Withings OAuth2 授权地址（纯函数）。
- `auth.exchange`：用授权码换取 token（需要 `network` 权限）。
- `fetch`：调用 Withings `measure/getmeas` 拉取测量（需要 `network` 权限）。
- `import`：解析调用方提供的 getmeas JSON（离线，不发网络请求）。
- `stats` / `measurements.list`：声明式 UI 页面/组件数据。

## 测量类型映射

| Withings type | 字段 | 单位 |
|---|---|---|
| 1 | `weightKg` | kg |
| 4 | `heightM` | m |
| 5 | `fatFreeMassKg` | kg |
| 6 | `fatRatioPct` | % |
| 8 | `fatMassKg` | kg |
| 9 | `diastolicMmHg` | mmHg |
| 10 | `systolicMmHg` | mmHg |
| 11 | `heartRateBpm` | bpm |
| 12 | `temperatureC` | °C |

值按 Withings 约定 `value × 10^unit` 缩放到 UCUM 单位；未知类型被忽略，全部未知则报错。

## 依赖与隐私

`requests`、`requests-oauthlib`，只装进本模块独立 venv。token 由核心/用户提供，
不落盘、不写日志；健康数据默认不出本机。非医疗器械，不用于诊断。

## 许可

适配层 GPL-3.0-only；上游 MIT，见 `NOTICE`。

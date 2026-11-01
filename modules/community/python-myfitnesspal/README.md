# MyFitnessPal Diary Import · io.github.coddingtonbear.myfitnesspal

MyFitnessPal 饮食日记数据源，适配自
<https://github.com/coddingtonbear/python-myfitnesspal>。
仅导入用户本人的日记，作为营养记录进入 eclipse health。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `fetch`：用用户名/密码登录并抓取指定日期的日记（需要 `network` 权限）。
- `import`：解析调用方提供的日记 JSON（离线，不发网络请求）。
- `stats` / `diary.list`：声明式 UI 页面/组件数据。

## 依赖

`myfitnesspal`、`lxml`、`cloudscraper`，只装进本模块独立 venv。
缺依赖时 `health` 返回 `dependency.available=false`，`fetch` 返回
`MODULE_DEPENDENCY_MISSING`；`import` 与纯解析仍可用。

## 风险

- 非官方抓取，违反第三方服务条款或被 Cloudflare 拦截的风险由用户承担。
- 凭据只在调用期间存在于内存，不落盘、不写日志。
- 页面结构变化可能导致抓取失败；失败会返回可读错误，不静默返回空数据。
- 非医疗器械，不用于诊断。

## 许可

适配层 GPL-3.0-only；上游 MIT，见 `NOTICE` 与 `LICENSES/python-myfitnesspal-upstream.txt`。

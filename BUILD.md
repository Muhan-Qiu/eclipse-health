# 构建与安装（Windows）

本文件描述如何把 `npm run tauri dev` 形态的应用，变成可双击安装/启动的 Windows 应用。
构建链：**PyInstaller sidecar → Tauri externalBin → NSIS/MSI**。

## 1. 前置条件

| 依赖 | 版本 / 说明 |
|---|---|
| Windows | 10/11 x64（当前只支持 Windows） |
| Node.js | ≥ 20（本机 24.x），含 npm |
| Rust | stable + MSVC 工具链（`x86_64-pc-windows-msvc`） |
| Visual Studio Build Tools | 安装「使用 C++ 的桌面开发」 |
| WebView2 Runtime | Win11 自带；Win10 可能需安装 |
| Python venv | `backend/.venv`，已安装 dev 依赖（含 PyInstaller） |
| NSIS / WiX | Tauri CLI 首次构建时自动下载；离线环境需预置 |

确认工具链：

```powershell
npm --version
cargo --version
rustc -vV          # host 应为 x86_64-pc-windows-msvc
backend\.venv\Scripts\python.exe -m PyInstaller --version
```

## 2. 开发模式（不变）

```powershell
npm run tauri dev
```

debug 构建继续使用 `backend/.venv/Scripts/python.exe` 启动 uvicorn（端口 8765），
退出时按进程树结束。为了满足 Tauri `externalBin` 的构建期校验，`src-tauri/build.rs`
会在 debug 构建时创建一个**空占位** `src-tauri/binaries/eclipse-health-backend-<triple>.exe`；
它不会被 dev 启动，也不影响 release。

## 3. 一键构建安装包

```powershell
powershell -File scripts\build_release.ps1            # 默认 NSIS
powershell -File scripts\build_release.ps1 -Bundles msi
powershell -File scripts\build_release.ps1 -Bundles all
```

脚本按顺序执行，任一步失败即停：

1. **PyInstaller**（onedir）→ `backend/packaging/dist/eclipse-health-backend/`
   （`eclipse-health-backend.exe` + `_internal/`）
   - spec：`backend/packaging/eclipse-health-backend.spec`
   - 入口：`backend/packaging/serve.py`
2. 拷贝为 Tauri externalBin 命名：
   `src-tauri/binaries/eclipse-health-backend-x86_64-pc-windows-msvc.exe`；
   并把 `_internal/` 同步到 `src-tauri/_internal/`（Tauri resources，安装后与 sidecar 同级）
3. `npm run tauri build`（`beforeBuildCommand` 会先 `npm run build`）
   → `src-tauri/target/release/bundle/nsis/eclipse health_<version>_x64-setup.exe`、`.../msi/*.msi`

release 构建时如果 sidecar 缺失，`build.rs` 会直接报错（避免产出装好却起不来的包）。

### sidecar 里带了什么

`serve.py` 冻结后从 `sys._MEIPASS`（onedir 下即 `_internal/`）解析：

```
backend/resources/models/cardia        # 模型 + preprocess/model_config
backend/resources/samples              # MIT-BIH 100/200/208（调试/冒烟）
modules/official/cardia                # 官方 Cardia 模块源码，启动时安装到数据目录
eclipse_health_backend/modules/module.schema.json
```

- 启动前若数据目录没有 `org.eclipsehealth.cardia`，从随包源码重新打包成 `.ehmod` 安装；
- 模块 worker 不再依赖系统 Python：模块宿主用 `sys.executable` 启动 `src/main.py`，
  冻结后这个 `sys.executable` 就是 sidecar 自己，`serve.py` 识别后 `runpy` 直接执行脚本。

## 4. 运行时目录与进程

| 项 | 路径 |
|---|---|
| 数据（SQLite/波形/报告/模块） | `%LOCALAPPDATA%\eclipse-health` |
| 后端日志 | `%LOCALAPPDATA%\eclipse-health\logs\backend.log` |
| 模块日志 | `%LOCALAPPDATA%\eclipse-health\logs\modules\*.log` |
| 桌面偏好 | `%APPDATA%\com.eclipsehealth.app\desktop-settings.json` |
| dev 数据（隔离） | `backend/.data` |

- 端口固定 `127.0.0.1:8765`（前端构建时已写死）；若该端口已是本后端则复用，
  被其他进程占用时分析功能可能不可用。
- 主窗口在 `GET /api/v1/health` 返回 200 后显示（安装版实测 5.1 秒；模块已装时再快），
  90 秒仍未就绪也显示（便于看到错误态）；`/engine` 约再 7–10 秒 ready。
- 托盘「退出」会 `taskkill /T /F` 结束 sidecar 及其模块 worker。

## 5. 冒烟测试

```powershell
# 直接运行 release 可执行文件（sidecar 与 _internal 必须同目录）
.\src-tauri\target\release\v3.exe

# 安装包安装到当前用户后（开始菜单/桌面快捷方式名为 “eclipse health”）：
& "$env:LOCALAPPDATA\eclipse health\v3.exe"

# 另一个终端
backend\.venv\Scripts\python.exe backend\packaging\smoke.py --base http://127.0.0.1:8765
```

> 主程序文件名沿用 Cargo crate 名 `v3.exe`（Tauri 只把 productName 用于安装包、
> 快捷方式和窗口标题）；sidecar 是 `eclipse-health-backend.exe`。

`smoke.py` 会：健康检查 → 等 `/engine` ready → 导入 MIT-BIH 100 → 发起分析 → 轮询完成，
并打印心搏数、测量数与耗时。

安装包验证：安装到当前用户 → 启动 → 检查主窗口、记录页、托盘 → 退出后
`netstat -ano | findstr :8765` 应无监听。

## 6. 通知 / 设置命令 / 自动更新

- **通知**：已注册 `tauri-plugin-notification`，capability 含 `notification:default`。
  前端：`import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification"`。
- **设置命令**（B4-04 设置页）：`invoke("get_desktop_settings")`、
  `invoke("set_close_to_tray", { enabled })`、`invoke("set_splash_enabled", { enabled })`。
  返回 `{ closeToTray, splashEnabled }`，持久化到上表的 `desktop-settings.json`，重启保留。
- **自动更新**：`tauri-plugin-updater` 已注册，capability 含 `updater:default`，
  `tauri.conf.json` 里是空占位（`endpoints: []`、`pubkey: ""`）。**默认不可用**，
  没有签名私钥与更新服务器时不会尝试联网。启用步骤：
  1. `npm run tauri signer generate -- -w ~/.tauri/eclipse-health.key`，保存私钥与公钥；
  2. 在 `tauri.conf.json` 的 `plugins.updater` 填入 `pubkey` 与更新服务器 `endpoints`
     （静态 JSON，形如 `https://example.com/eclipse-health/{{target}}/{{arch}}/{{current_version}}`）；
  3. `bundle.createUpdaterArtifacts` 设为 `true`，构建时用
     `TAURI_SIGNING_PRIVATE_KEY`（+ `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`）签名；
  4. 把 `latest.json` 与安装包上传到更新服务器。
  私钥不得提交到仓库。

## 7. 常见错误

| 现象 | 原因 / 处理 |
|---|---|
| `sidecar missing: ...`（release） | 未先跑 `scripts/build_release.ps1`；或 `rustc -vV` 的 host triple 与文件名不一致 |
| 安装后窗口出现但记录页报连接失败 | sidecar 启动失败；看 `%LOCALAPPDATA%\eclipse-health\logs\backend.log` |
| `port 8765 is occupied by another process` | 关闭占用进程（`netstat -ano | findstr :8765`），或先结束残留的 dev 后端 |
| PyInstaller 报 `SubprocessDiedError` / `Memory allocation failed` | 机器内存/页文件紧张；关闭并行构建或设置 `OPENBLAS_NUM_THREADS=2` 后重试 |
| `cargo check` 在 release 下要求 sidecar | 预期行为；debug 会自动创建空占位 |
| MSI 构建失败 | 首次构建需要 WiX（Tauri CLI 自动下载）；可先用 `-Bundles nsis` |
| 模块预热一直 warming | 看模块日志；ONNX 首次初始化约 1–3 秒，若报 OpenBLAS 分配失败是系统内存不足 |

## 8. 已知限制

- onedir sidecar 安装后约 595 MB（含 litellm/pydantic_ai/matplotlib/onnxruntime）；
  NSIS 压缩后安装包 211 MiB。选 onedir 是为了避免 onefile 每次启动解压（实测冷启动 28s → 数秒）。
- `_internal/` 与 sidecar 必须同级；`scripts/build_release.ps1` 会自动同步。
- 端口固定 8765，不支持多实例同时运行（单实例插件只保留一个）。
- 未做代码签名；Windows SmartScreen 可能提示未知发布者。
- 自动更新未启用（见 §6）。

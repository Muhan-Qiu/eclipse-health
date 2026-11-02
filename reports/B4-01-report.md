# B4-01 报告 · 打包与安装包（PyInstaller sidecar + Tauri）

> 完成时间：2026-10-30 · 平台：Windows 11 x64 · 工具链 `x86_64-pc-windows-msvc`
> 结论：**可安装、可启动、能分析**。NSIS 安装包已产出并完成安装/启动/分析/退出验证。

## 1. 产物

| 产物 | 路径 | 大小 |
|---|---|---|
| NSIS 安装包 | `src-tauri/target/release/bundle/nsis/eclipse health_0.1.0_x64-setup.exe` | 221,757,743 B（211.5 MiB） |
| 后端 sidecar（onedir） | `backend/packaging/dist/eclipse-health-backend/` | 594.5 MB（exe 84,894,738 B + `_internal/`） |
| Tauri externalBin 副本 | `src-tauri/binaries/eclipse-health-backend-x86_64-pc-windows-msvc.exe` | 84.9 MB |
| 免安装版 | `src-tauri/target/release/v3.exe` + `eclipse-health-backend.exe` + `_internal/` | 17.5 MB + 594.5 MB |

> 主程序文件名沿用 Cargo crate 名 `v3.exe`；Tauri 只把 productName 用于安装包名、快捷方式和窗口标题。
> 安装位置：`%LOCALAPPDATA%\eclipse health\`；卸载后用户数据 `%LOCALAPPDATA%\eclipse-health` 保留。

## 2. 构建耗时

| 阶段 | 耗时 |
|---|---|
| PyInstaller（onedir，`--clean`） | 727.5 s（≈12 分） |
| Tauri build（Rust release：LTO/单 codegen unit） | 598.1 s（≈10 分，其中 Rust 编译 3 分 29 秒） |
| 安装包安装（NSIS `/S`） | 38.6 s |

机器同时有两条深度学习训练任务占 CPU，实际耗时偏乐观/保守各半；无并行负载时 Rust 增量构建会更快。

## 3. 冒烟测试（全部实测）

### 3.1 安装版

1. `eclipse health_0.1.0_x64-setup.exe /S` → 退出码 0，安装到 `%LOCALAPPDATA%\eclipse health`。
2. 启动 `v3.exe`：
   - `GET /api/v1/health` 200：**5.14 s**；
   - `/engine` ready：再 **7.8 s**（`model=cardia-2.0 mode=module`）。
3. `backend/packaging/smoke.py`：导入 MIT-BIH `100`（650,000 样本 @ 360 Hz）→ 分析完成
   - **beats=2270，measurements=15，分析耗时 4,561 ms，全流程 5.6 s**。
4. 关闭窗口（`closeToTray=false`）→ 主进程退出，sidecar 与模块 worker 均结束，8765 无监听。
5. `uninstall.exe /S` → 退出码 0，安装目录已删除；`%LOCALAPPDATA%\eclipse-health` 数据保留。

### 3.2 免安装版

- 冷启动（数据目录已存在）：**3.4–4.7 s** 到健康检查 200。
- 托盘行为：`closeToTray=true` 时关窗后主进程与 sidecar 均存活（收起到托盘）；`false` 时完整退出并清理子进程。
- 首次启动（全新数据目录、sidecar 直跑、端口 8767）：2.8–3.3 s 健康检查可用，启动前自动把官方 Cardia 模块从包内源码安装到数据目录（`org.eclipsehealth.cardia 1.0.0 state=enabled`），`/engine` 后续正常 ready。

### 3.3 回归

| 命令 | 结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` | 通过（exit 0，2 skipped） |
| `npm run build`（tsc + vite） | 通过；`dist/` ≈ 1.27 MB JS + 140 kB CSS |

## 4. 桌面增强状态

- **通知**：`tauri-plugin-notification` 已注册，capability 含 `notification:default`，前端依赖 `@tauri-apps/plugin-notification` 已装。
- **设置命令**：`get_desktop_settings` / `set_close_to_tray` / `set_splash_enabled` 已实现，持久化到 `%APPDATA%\com.eclipsehealth.app\desktop-settings.json`，重启保留；托盘勾选项与命令双向同步。
- **自动更新**：`tauri-plugin-updater` 已注册、capability 含 `updater:default`；`tauri.conf.json` 中 `endpoints: []`、`pubkey: ""` 空占位，**默认不联网**。启用步骤见 `BUILD.md §6`。
- **闪屏/白闪**：窗口 `visible:false` + 健康检查通过后显示；release 下 90 s 兜底显示。

## 5. 失败点与处理

1. **前端 TS 编译阻塞打包**（非本任务文件）：
   - `src/features/modules/api.ts:121` `buildQuery` 不接受 boolean；
   - `src/components/records/waveform-viewer.tsx` 3 处 `onViewChange` 回调签名与 `OverviewStrip`/`LeadStrip` 的 `(view: [number, number])` 不一致。
   - 处理：最小改动（`String(keepData)`、`([start, end]) => applyView(start, end)`）。`BUILD.md` 的验收命令要求 `npm run build` 通过，故必须修。
2. **`scripts/build_release.ps1` 收尾报错**：StrictMode 下单个产物时 `$Artifacts.Count` 抛 `PropertyNotFoundStrict`，安装包其实已成功。已改为 `@(...)` 强制数组。
3. **端口竞态**：测试期间另一开发后端抢先占用 8765，sidecar 启动完成后 bind 失败退出（日志 `WinError 10048`），Tauri 复用了该健康后端导致健康检查指向 dev 数据目录。清理占用进程后重测通过。生产环境单实例 + 健康检查逻辑符合预期，但**启动时若 8765 被其他进程占用，应用会复用而不是报错**——这是既有设计，B5 可考虑提示用户。
4. **模块安装的临时路径异常**：把数据目录放在仓库内（含并发文件监听/杀毒扫描的路径）时，`.staging` → `1.0.0` 的目录 rename 报 `WinError 5`，模块装不上；换成 `%LOCALAPPDATA%`、`C:\Users\...\eh-smoke-ascii`、`C:\Users\...\eh-测试` 均正常。判断为环境级文件句柄/扫描冲突，非代码路径问题；生产默认数据目录不受影响。
5. **首次真冷启动**：磁盘冷 + 双训练任务 + 模块首次安装时，sidecar 就绪约 85 s（该次因端口冲突未成功）；模块安装本身仅 0.16 s，后续启动 3–5 s。`BUILD.md` 已更新实测值。

## 6. 未做 / B5 待办

- 代码签名（SmartScreen 会提示未知发布者）。
- 自动更新服务端与签名私钥（占位已就绪，未启用）。
- MSI 构建未验证（脚本支持 `-Bundles msi`，本机只跑了 NSIS）。
- macOS/Linux、安装器 UI 定制、每模块 venv、通知的页面级调用（B4-07 负责）。
- 安装包 211 MiB / sidecar 595 MB 仍偏大，后续可按需裁剪 litellm/pydantic_ai/matplotlib，或改为按模块下载。

## 7. 复现命令

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm run build
powershell -File scripts\build_release.ps1            # 全量：PyInstaller + Tauri NSIS
powershell -File scripts\build_release.ps1 -SkipPyInstaller   # 只重打安装包
```

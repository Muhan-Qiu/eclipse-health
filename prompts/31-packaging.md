# B4-01 · 打包与安装包（PyInstaller sidecar + Tauri）

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B4 收口（单任务先跑）
> 目标：把当前 `tauri dev` 才能跑的应用，变成可双击安装/启动的 Windows 应用。UI 功能不再扩展。

## 1. 必读

- `reports/B2-04-report.md`（桌面壳、dev 后端子进程、白闪处理）
- `reports/B2-01-report.md`（模块自动安装、分析服务、`/engine`）
- `reports/B3-01-report.md`（简化权重、`EH_CARDIA_MODEL_PATH`）
- `src-tauri/tauri.conf.json`、`src-tauri/src/lib.rs`、`src-tauri/Cargo.toml`
- `backend/pyproject.toml`、`backend/src/eclipse_health_backend/app.py`、`analysis_service/bridge.py`、`modules/registry.py`
- `scripts/pack_cardia.py`

## 2. 目标

1. 后端打成独立 sidecar（不依赖系统 Python/venv）。
2. Tauri 生产构建自动带 sidecar、模型、Cardia 模块；安装后启动即用。
3. 开发模式仍可用 `npm run tauri dev`，不破坏现有流程。

## 3. 你必须交付

1. **PyInstaller 后端**
   - `backend/packaging/serve.py` 作为冻结入口：设置生产 `EH_DATA_DIR`（默认 `%LOCALAPPDATA%\eclipse-health`）、端口、日志目录；启动前确保 Cardia 模块已安装（从随包的 `.ehmod` 或 `modules/official/cardia` 安装到 data dir），再启动 uvicorn。
   - `backend/packaging/eclipse-health-backend.spec`：收集 `eclipse_health_backend`、uvicorn、sqlmodel、onnxruntime、wfdb、neurokit2、scipy、matplotlib、PIL、litellm、pydantic_ai、sse_starlette 等；排除 tests/dev 工具；包含 `resources/models/cardia`（简化图）与 Cardia 模块/`.ehmod`。
   - 输出到 `src-tauri/binaries/eclipse-health-backend-x86_64-pc-windows-msvc.exe`（Tauri externalBin 命名）。
   - 允许在 `backend/pyproject.toml` 补 `matplotlib`、`Pillow`、`Jinja2` 为直接依赖（venv 已装）。
2. **Tauri 生产接线**
   - `tauri.conf.json`：`bundle.externalBin` 指向 sidecar；`resources` 如需要带 `.ehmod`/模型；保留现有图标/窗口/托盘配置。
   - `src-tauri/src/lib.rs`：
     - debug 仍走现有 `backend/.venv/Scripts/python.exe`；
     - release 启动随机/固定空闲端口（建议 8765，先探测占用），用 `current_exe().parent()` 找 sidecar，设置 `EH_DATA_DIR`，健康检查通过后再显示主窗口；退出时结束子进程。
     - 不引入 `tauri-plugin-shell` 也能做（std::process）；如用插件，补 capability。
   - 生产数据目录与 dev 隔离：`%LOCALAPPDATA%\eclipse-health`；日志 `logs/`；不要写入安装目录。
3. **构建脚本**
   - `scripts/build_release.ps1`（或 `.py`）：打包后端 → 拷贝 sidecar → `npm run tauri build`；失败即停并打印原因。
   - README/`BUILD.md` 写：前置条件、命令、产物位置、常见错误。
4. **冒烟测试**
   - 构建 NSIS/MSI 安装包；安装到当前用户（或解压免安装版）启动：
     - 主窗口出现、`GET /health` 200、记录页空状态正常、关闭到托盘、退出后 sidecar 进程结束。
     - 导入并分析一条 `backend/resources/samples/100`（可从开发目录手动选/或用 API），确认模型与模块在冻结环境可用。
   - 记录冷启动耗时、安装包大小、sidecar 大小。
5. **桌面增强（与 B4-04/B4-07 的契约）**
   - 通知：加 `tauri-plugin-notification` + capability；前端可 `sendNotification`（B4-07 调用）。
   - 设置命令：暴露 `get_desktop_settings` / `set_close_to_tray(enabled)` / `set_splash_enabled(enabled)`，持久化到应用配置目录（JSON 或 store）；B4-04 的设置页会 `invoke` 这些命令。命令不存在时前端有本地回退，但你应提供。
   - 自动更新：加 `tauri-plugin-updater` 配置占位（endpoint/pubkey 从环境/配置读）；**没有签名私钥和更新服务器时不要启用**，构建仍要成功。写清楚启用步骤。
6. **报告**：`reports/B4-01-report.md`：产物路径/大小、构建耗时、冒烟步骤、通知/设置/更新状态、失败点、未做项。

## 4. 文件所有权（只能改这些）

```
backend/packaging/**
scripts/build_release.ps1（或 .py）
src-tauri/**
backend/pyproject.toml          # 仅补直接依赖
package.json / package-lock.json # 仅 Tauri 插件
BUILD.md
reports/B4-01-report.md
```

不要动：`src/**`（页面/组件/API/i18n）、`backend/src/**` 的业务逻辑（如果冻结入口必须加钩子，放在 `backend/packaging/`，不要改核心）、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm run build
powershell -File scripts\build_release.ps1
# 安装/解压产物启动，验证健康检查、导入分析、退出清理
```

报告写：安装包与 sidecar 绝对路径/大小、冷启动、模块自动安装日志、失败与绕行、B5 待办。

## 6. 明确不做

自动更新（H5）、代码签名、macOS/Linux、安装器 UI 定制、通知、模块安装 UI、页面功能改动、每模块 venv。只做「可安装、可启动、能分析」。

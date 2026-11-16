# eclipse health

本地优先的桌面健康应用：导入 ECG、用 Cardia 模型做分析、把记录/趋势/报告放在一个离线可用的界面里。数据保存在本机，没有遥测。

当前版本 `0.1.3`，面向 Windows 桌面端（Tauri 2 + React 19 + TypeScript，后端为本地 Python sidecar）。

## 功能范围

- **导入**：WFDB（`.hea`/`.dat`/`.atr`）、CSV、EDF、SCP-ECG，以及 Apple 健康心电图 CSV、Samsung、华为手表导出（厂商格式标 `experimental`，见「已知限制」）。支持自动探测格式与导入预览。
- **分析**：内置 Cardia 2.0 ONNX 模型（信号质量、R 峰/心搏、心率与间期测量）；引擎列表来自后端注册表，可指定引擎重新分析。
- **记录**：列表、时间/设备/标签筛选、收藏、详情波形与导联切换、软删除。
- **趋势与对比**：按时间查看指标变化，记录之间对比。
- **报告**：生成 PDF / PNG 报告并保存到本地。
- **助手**：可选接 OpenAI、Anthropic 或本地 Ollama；API Key 以 Windows DPAPI 加密存储。只向模型发送摘要与测量，不发送波形、备注或成员姓名。
- **模块**：安装/卸载 `.ehmod` 模块（含官方 Cardia 分析模块），查看权限与审计日志；每个已安装模块都有独立工作台（`/modules/:id`），侧栏可直达，工作台内可查看声明式页面、仪表盘卡片、模型卡、试运行模块工具、管理权限与审计；模块通过 stdio JSON-RPC 在独立进程中运行。
- **助手模块选择**：对话输入区「+」可选择本轮优先使用的模块；所选模块的工具会排在工具目录前面并写入系统提示词，其他已安装模块的工具仍然可用。
- **数据管理**：ZIP / JSON / CSV 备份与恢复、隐私清理、诊断日志导出。

## 安装与运行

需要 Windows 10/11。仓库开发需要 Node.js 20.19+（本机验证为 v24）、Python 3.12。

安装包（NSIS/MSI/免安装 ZIP）由发布轮统一构建；安装后直接启动 `eclipse health`，后端 sidecar 会自动在 `127.0.0.1:8765` 启动。

### 从源码运行（V4.3）

本目录就是 V4.3 应用端。`node_modules`、`backend\.venv`、`src-tauri\binaries`、`src-tauri\target` 通过 Windows 目录联接共享 V4.2 的依赖/构建缓存，避免重复占用空间。共享 venv 里的 editable 路径仍指向 V4.2，所以**必须用下面的脚本启动后端**，确保加载的是 V4.3 的 `backend\src`。

```powershell
# 一键：新窗口启动 V4.3 后端 + 当前窗口启动前端
.\run-dev.cmd

# 或分两个终端：
.\run-backend.cmd          # 或 npm run backend
npm run dev                # http://localhost:1420
```

如果 8765 已被另一个后端占用（例如已安装的 V4.2 应用仍在运行），用 8766 测试：

```powershell
.\run-dev-8766.cmd
# 或
.\run-backend-8766.cmd
$env:VITE_API_BASE = "http://127.0.0.1:8766/api/v1"
npm run dev
```

`npm run tauri dev` 使用 `src-tauri\binaries` 里的 sidecar；该二进制目前仍是 V4.2 构建的。要测试 V4.3 的后端改动，请用上面的 Web 开发方式，或重新构建 sidecar。

### 构建与检查

```powershell
npm run build
npm run check:modules
npm run check:packages

# 测试/ruff 也要把 V4.3 的 backend\src 放在最前
$env:PYTHONPATH = "$PWD\backend\src"
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m ruff check backend
```

### 数据位置

- 开发运行：`backend\.data\`
- 安装版：`%LOCALAPPDATA%\eclipse-health\`（可用 `EH_DATA_DIR` 覆盖）

## 数据与隐私

- 记录、波形、分析结果、报告全部存在本机 SQLite 与文件目录，不上传、不做遥测。
- 删除记录先做软删除（从列表隐藏，文件仍在本地）；需要彻底移除时用隐私页的「清空数据」，会删除记录、波形、分析与报告。
- LLM 助手默认不启用；只有用户配置了 provider 并发起对话时才会联网，且发送内容限于摘要/测量/质量/警告。
- 导入时只保存文件哈希，不保留原始文件名。

## 已知限制

- **自动更新（H5）未启用**：需要签名私钥与更新服务器，当前安装包不含更新端点和公钥。
- **厂商格式未做真机验证（G3）**：Apple / Samsung / 华为适配器代码就绪，但缺少真实设备导出样本，标记为 `experimental`；解析失败时请保留原始文件用于后续修正。
- **安装包未签名**：SmartScreen 会提示「未知发布者」，选择「更多信息 → 仍要运行」即可。

更多设计文档见 `docs/`（模块契约、数据 Schema、UI 规范等）。

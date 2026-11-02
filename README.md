# eclipse health

本地优先的桌面健康应用：导入 ECG、用 Cardia 模型做分析、把记录/趋势/报告放在一个离线可用的界面里。数据保存在本机，没有遥测。

当前版本 `0.1.0`，面向 Windows 桌面端（Tauri 2 + React 19 + TypeScript，后端为本地 Python sidecar）。

## 功能范围

- **导入**：WFDB（`.hea`/`.dat`/`.atr`）、CSV、EDF、SCP-ECG，以及 Apple 健康心电图 CSV、Samsung、华为手表导出（厂商格式标 `experimental`，见「已知限制」）。支持自动探测格式与导入预览。
- **分析**：内置 Cardia 2.0 ONNX 模型（信号质量、R 峰/心搏、心率与间期测量）；引擎列表来自后端注册表，可指定引擎重新分析。
- **记录**：列表、时间/设备/标签筛选、收藏、详情波形与导联切换、软删除。
- **趋势与对比**：按时间查看指标变化，记录之间对比。
- **报告**：生成 PDF / PNG 报告并保存到本地。
- **助手**：可选接 OpenAI、Anthropic 或本地 Ollama；API Key 以 Windows DPAPI 加密存储。只向模型发送摘要与测量，不发送波形、备注或成员姓名。
- **模块**：安装/卸载 `.ehmod` 模块（含官方 Cardia 分析模块），查看权限与审计日志；模块通过 stdio JSON-RPC 在独立进程中运行。
- **数据管理**：ZIP / JSON / CSV 备份与恢复、隐私清理、诊断日志导出。

## 安装与运行

需要 Windows 10/11。仓库开发需要 Node.js 20.19+（本机验证为 v24）、Python 3.12。

安装包（NSIS/MSI/免安装 ZIP）由发布轮统一构建；安装后直接启动 `eclipse health`，后端 sidecar 会自动在 `127.0.0.1:8765` 启动。

### 从源码运行

```powershell
# 后端（项目根目录执行，依赖已在 backend/.venv）
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --host 127.0.0.1 --port 8765

# 前端 Web 预览（另一个终端）
npm run dev                 # http://localhost:1420

# 桌面端开发（Tauri 会自动拉起上面的后端命令）
npm run tauri dev
```

### 构建与检查

```powershell
npm run build                                        # tsc + vite build，产物在 dist/
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

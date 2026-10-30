# eclipse health 0.1.0 · 发布说明（草稿）

> 状态：草稿。安装包由发布轮统一构建，文件大小与 SHA-256 在打包后填入文末表格。

## 这次带来什么

- **导入**：WFDB、CSV、EDF、SCP-ECG；Apple 健康心电图 CSV、Samsung、华为手表导出（厂商格式为 `experimental`）。支持拖拽/选择文件、格式自动探测、导入前预览。
- **分析**：内置 Cardia 2.0 模型，输出信号质量、R 峰/心搏与心率/间期测量；引擎列表按后端注册表展示，可切换引擎重新分析。
- **记录**：记录库、详情（波形与导联、分析结果）、按时间/设备/标签筛选、收藏、软删除。
- **趋势与对比**：指标随时间变化，记录之间并排对比。
- **报告**：生成 PDF / PNG 报告并保存到本地。
- **助手**：可选 OpenAI、Anthropic 或本地 Ollama。回复中的工具调用过程可见；API Key 用 Windows DPAPI 加密，只发送摘要与测量，不发送波形、备注或姓名。
- **模块**：安装/卸载 `.ehmod`，查看权限与审计；官方 Cardia 分析模块随包预装，可在模块页卸载或替换。
- **数据管理**：ZIP / JSON / CSV 备份与恢复、隐私清理、诊断日志导出。

## 安装

1. 系统要求：Windows 10/11 x64。
2. 运行安装包（NSIS/MSI）或解压免安装 ZIP，启动 `eclipse health`；后端 sidecar 会自动在本机 `127.0.0.1:8765` 启动，无需单独安装 Python。
3. 安装包未签名，SmartScreen 可能提示「未知发布者」：选择「更多信息 → 仍要运行」。

数据保存在 `%LOCALAPPDATA%\eclipse-health`，卸载时不会删除；需要彻底清除请先备份再手动删除该目录。

## 已知限制

- **自动更新未启用**：当前版本不检查也不下载更新，需要手动安装新版本。启用前需要签名私钥与更新服务器。
- **厂商格式未经真机验证**：Apple / Samsung / 华为适配器为 `experimental`，缺少公开真机导出样本；如解析失败，请保留原文件以便修正。
- **仅 Windows**：桌面端目前只构建 Windows 版本。
- **仅有 Cardia 一个分析引擎**：第三方引擎需以模块形式安装；引擎切换/重新分析框架已就绪。
- **未签名**：首次运行可能触发 SmartScreen 提示。

## 文件与校验和

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `eclipse health_0.1.0_x64-setup.exe`（NSIS） | 待填 | 待填 |
| `eclipse health_0.1.0_x64_en-US.msi`（MSI，可选） | 待填 | 待填 |
| `eclipse-health_0.1.0_x64-portable.zip`（免安装） | 待填 | 待填 |

> 校验命令（PowerShell）：`Get-FileHash .\eclipse health_0.1.0_x64-setup.exe -Algorithm SHA256`

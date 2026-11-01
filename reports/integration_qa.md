# A9 · 合并验收报告（集成 QA）

日期：2026-11-02　分支：`feat/ui-alignment`（未合入 main 前的工作区验收）
结论：**功能验收通过，可以今天上线**；上线动作（新安装包 + 官网文案 + 公开树）已在本次验收内执行，结果见第 6 节。

## 1. 自动检查

| 命令 | 结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` | **1114 passed, 0 failed, 0 errors, 16 skipped**（673.7 s） |
| `backend\.venv\Scripts\python.exe -m ruff check backend` | All checks passed |
| `npm run build`（tsc + vite） | 通过 |

仅剩既有 FastAPI duplicate operation id 警告（exercises / memory），与本轮无关。

## 2. 功能验收（真实后端 + Vite + Playwright）

| 项 | 结果 |
|---|---|
| 标准导入 WFDB | `100.hea` 预览 200：2 导联、360 Hz、1805 s |
| 标准导入 CSV / Apple Health | Apple ECG CSV 预览 200、提交 201、记录列表可见 |
| 标准导入 EDF | `mitdb100-1lead-10s.edf` 预览 200：1 导联、360 Hz、10 s |
| AI 导入 CSV（UI） | 预览 2 条心率 → 「写入选中记录」成功 2 → 健康数据页可见 62/68 bpm |
| AI 导入 HTML / PDF | 结构化样例各 2 条（心率 + 血压）→ 提交成功，记录可查；重复提交返回 0 created / 2 skipped（幂等） |
| 服务商预设 | 35 个预设；DeepSeek / Ollama / OneAPI 保存成功，字段由预设补齐；旧 provider 无 presetId 仍可用；Mock「测试连接」成功（0 ms，模型可用、支持工具调用） |
| 模块市场 | 应用 官方 10 / 社区 22，与线上索引一致；安装官方 `io.github.mit-lcp.wfdb` + 社区 `io.github.grubersjoe.activity-calendar` 成功 |
| 自定义卡片 | 创建压力 / 血氧卡片，首页显示真实值 42（单位未知）与 97 %，1 个数据点 |
| UI 对齐 | 1024/1280/1440 均 `docOverflow=0`、`mainOverflow=0`；同排卡片底边完全一致（如 Stress/SpO₂/最近记录） |
| 官网 | `/`、`/en/`、模块页、开发者页、4 份模块文档、索引与 `.ehmod` 均 200；官方/社区标签显示 10/22；提示词生成器在浏览器内生成 |

## 3. 本轮修复的集成问题（只修集成，不改需求）

1. **文件选择完全无效（阻塞）**：`import-provider.tsx` 在读取前执行 `event.target.value = ""`，Chrome 会清空同一个 `FileList`，导致选择文件/文件夹后 `files.length=0`、没有任何请求。改为先读取再清空；文件与文件夹两个 input 均已修复。
2. **导入后健康数据页不刷新（阻塞验收）**：提交不经过 react-query。新增 `refreshImportedData()`，标准导入与 AI 导入提交后 invalidate `health-records` / `records` / `trends` / `dashboard cards`。实测 AI 导入关闭弹窗后计数 8 → 10，无需刷新。
3. **官网仍写「安装包待上传」**：Release `v0.1.0-alpha` 已有安装包。已更新中英文首页文案与版本标记为「已发布」。
4. **交接文档条数过期**：`website-handoff` 中「32 条官方」改为官方 10 + 社区 22，「安装包待上传」改为已发布。

## 4. 安全项

| 项 | 结果 |
|---|---|
| 明文 Key | 磁盘仅 `dpapi:v1:` 密文；日志、审计、返回值、仓库均未发现明文 key |
| 健康数据外发 | 未发现遥测；`telemetryEnabled` 强制 false；AI 导入只发文件清单/文本片段；本轮所有请求仅到 `127.0.0.1` |
| Agent 沙箱 | 工具层路径校验（拒绝绝对路径/`..`/盘符/符号链接）与 24 h 清理有效；**Windows 下不是 OS 级文件沙箱，脚本仍可 `open()` 任意路径**，此限制已在 `docs/IMPORT_AGENT_API.md` 声明 |
| 日志 | 审计仅记录文件数、字节数、类型、provider、工具次数、耗时；不含波形、文件名、备注 |

## 5. 发布状态

| 项 | 状态 |
|---|---|
| 索引签名 | 仍为 **dev-2026**（未换生产钥，如实记录） |
| GitHub Release | `v0.1.0-alpha` 已存在（旧构建） |
| gh-pages | 已更新；线上官方 10 / 社区 22，与本地索引内容一致 |
| 安装包 | 本次重新构建并替换 Release asset（含第 3 节修复） |

## 6. 上线动作（本次执行）

- 重跑 `scripts\build_release.ps1`（PyInstaller + Tauri NSIS），替换 `v0.1.0-alpha` 安装包与 `SHA256SUMS.txt`。
- 推送公开树到 `Muhan-Qiu/eclipse-health` main；推送官网到 `gh-pages`。
- 更新 `docs/RELEASE_NOTES_DRAFT.md` 与 `website-handoff` 状态。

## 7. 遗留 / 不阻塞

- Windows 沙箱无 OS 级文件隔离（既有设计，文档已声明）。
- 真实云端模型未在本机联调（无 provider key / Ollama），AI 解析用确定性脚本适配器验证完整 SSE→预览→提交链路；后端 37 个导入测试覆盖 CSV/HTML/PDF。
- 生产 Ed25519 重签与应用内置公钥替换仍需用户执行。

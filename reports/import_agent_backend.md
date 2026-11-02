# A5 · Agent 数据导入（后端沙箱）交付报告

状态：完成
日期：2026-11-01

## 交付物

| 文件 | 内容 |
|---|---|
| `docs/IMPORT_AGENT_API.md` | 前端 A6 的接口契约：4 个端点、SSE 事件、8 个工具、限制、错误码、样例 |
| `docs/HEALTH_RECORD_KINDS.md` | 15 种 kind 的 value/unit/范围/证据规则、ECG 规则、幂等键、单位别名 |
| `backend/src/eclipse_health_backend/import_agent/` | 完整实现（api / agent / tools / kinds / commit / store / sandbox / audit / limits / errors） |
| `backend/src/eclipse_health_backend/import_agent/sandbox_assets/` | 子进程 bootstrap（禁网/禁子进程）+ `eh_import_helpers`（CSV/JSON/XML/HTML/XLSX/PDF/ZIP） |
| `backend/tests/import_agent/` | 37 个测试（路径穿越、超时、超大输出、无网络、非法记录、幂等、provider、PDF、HTML、CSV、ECG） |
| `backend/pyproject.toml` / `packaging/eclipse-health-backend.spec` | 新增 `pypdf`、`openpyxl` 依赖与沙箱资源打包 |

## 接口

- `POST /api/v1/import-agent/sessions`：multipart `files[]` / `files` / `file` 或调试 `path`；
  复制到 `<data>/import-agent/<sessionId>/input/`，返回文件清单与 24h 过期时间。
- `POST /sessions/{id}/run`：SSE `status/token/tool_call/tool_result/preview/done/error`；
  最多 12 次工具调用、整轮 180 s。
- `POST /sessions/{id}/commit`：只接受 `propose_records` 产生过的候选；幂等。
- `GET /sessions/{id}`、`GET /sessions/{id}/proposals`、`GET /sessions`、`DELETE /sessions/{id}`。

已挂载到 `api/__init__.py`；导入失败时核心服务照常启动。

## 安全边界

- 输入文件复制到 session 的 `input/`；所有工具路径经 `safe_join`，拒绝绝对路径、`..`、
  反斜杠、盘符和符号链接。
- `run_python`：独立子进程、源码模式 `-I -B -X utf8`、冻结模式复用 sidecar 的 runpy 入口、
  清空环境变量（只保留 Windows 必需项）、cwd=`work/`、默认 120 s、stdout/stderr 各 64 KB、
  超时/取消用 `taskkill /T` / `killpg` 终止。
- 默认无网络：子进程 bootstrap 拦截 `socket.connect/create_connection/getaddrinfo`，
  并禁用 `subprocess` / `os.system` / `exec*` / `spawn*`。
  **文档明确说明：Windows 下不是 OS 级硬沙箱**，真正的边界是“文件副本 + 路径校验 + 候选再校验”。
- Agent 进程无数据库连接；只有 `propose_records` 产出候选，commit 由主进程重新校验后写入。
- 不把整份文件发给模型：模型只看到文件清单与 `read_text_file` 的文本片段；二进制不发送。
- 审计：每次建会话/运行/提交/放弃写 `<data>/audit/import-agent.jsonl`，并尽力写
  `audit_log`（`import_agent.*`），只记录计数、耗时、错误码、provider 类型。
- 清理：commit / DELETE 后删除 `input/ work/ output/`；24 h TTL 兜底。

## 记录与持久化

- `record_type = org.eclipsehealth.health.<kind>`，ECG 保持 `org.eclipsehealth.ecg`；
  复用现有 `records` / `signals` 表，没有平行表。
- 15 种 kind：steps、heart-rate、resting-heart-rate、sleep、body-mass、blood-pressure、
  spo2、stress、workout、respiratory-rate、body-temperature、blood-glucose、hrv、ecg、body。
- 单位归一（bpm→count/min、lbs→kg、kPa→mm[Hg]、°F→Cel、uV/V→mV 等），范围校验，
  证据必须指向本次上传文件（或 ZIP 子路径）。
- 幂等键：`sha256(fileHash | source | kind | startAt(UTC) | endAt(UTC) | canonical(value))`；
  按 `metadata.externalId` 跳过重复；同一 session 重复 commit 返回首次结果并带
  `duplicateCommit=true`。
- ECG：只有 `waveform` 指向 `output/` 下的 CSV/float32 才允许；转换到 mV、推断采样率，
  走现有 `create_record_from_parsed` 波形管线。PDF 只有报告时 `kind=ecg` 返回
  `ecg_waveform_required`，只能提数值类记录。

## 验证

- `pytest tests/import_agent`：**37 passed**。
- `ruff check src/eclipse_health_backend/import_agent tests/import_agent`：**All checks passed**。
- 三个样例跑通 SSE 预览 + 提交：
  - CSV（列名 `Date,Time,Pulse (bpm)`，按语义匹配 → 2 条 heart-rate）；
  - HTML 表格（心率 + 血压 → 2 条）；
  - 合成 PDF 报告（`Heart Rate` + `Blood Pressure` → 2 条数值记录，0 条 ECG）。
  - 额外：ECG CSV（1000 点，time 列推断 500 Hz）提交后信号表与文件均正确。
- 全量 `pytest tests`：导入 Agent 相关全绿；`tests/modules/test_official_pyhrv.py` 的 8 个
  用例失败，原因是本机中文路径在模块 worker 子进程中被错误编码（`can't open file`），
  与本批次代码无关，属于既有环境问题。

## 已知限制

- Windows 没有 OS 级沙箱；无法阻止恶意脚本直接读文件系统。已用文件副本、工具路径校验、
  候选再校验与审计降低风险，并在文档中如实声明。
- FIT 为二进制格式，未内置解析器；Agent 可在脚本中自行解析（或配置了 `fitparse` 时使用），
  失败会以工具错误返回，不影响其他格式。
- PDF 只提取文本（pypdf）；扫描版 PDF 需要 OCR，当前不支持，会得到空文本。
- v1 不支持多导联合并成一条 ECG 记录；每个 lead 单独提案。

## 需要指挥官/前端注意

1. A6 直接按 `docs/IMPORT_AGENT_API.md` 实现：上传 → 监听 SSE 展示 `tool_call`（含脚本代码）
   → `preview` 展示候选 → `commit`。
2. 默认建议本地 Ollama；没有 provider 时 run 返回 `409 provider_not_configured`。
3. 生产打包需重新跑 PyInstaller（spec 已加入 `pypdf`/`openpyxl` 与 `sandbox_assets`）。

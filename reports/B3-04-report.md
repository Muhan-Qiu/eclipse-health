# 报告 · B3-04 LLM 助手 + 工具调用可视化

状态：完成

## 交付

- `llm/providers.py`：provider 配置 + DPAPI 凭据。支持 `mock|ollama|openai|anthropic`；key 只以
  `dpapi:v1:<base64>` 存在 `<data>/secrets/providers.json`，API/日志/异常只出现「已配置」。
- `llm/tools.py`：6 个只读工具 `list_records / get_record / get_analysis / get_measurements /
  get_trends / get_model_card`。只返回摘要、测量、质量、警告；**不含波形、notes、成员姓名、标签原文**
  （标签只给数量）。越权/软删除统一 `NOT_FOUND`。
- `llm/agent.py`：系统提示（非诊断、引用工具结果、不编造）、最多 5 次工具调用、60s 截止、可取消；
  `stream_reply` 产出 `token/tool_call/tool_result/citation/done/error`。mock 适配器可完整演示
  list→analysis→measurements→回答；Ollama 走 `/api/chat` 流；openai/anthropic 走 LiteLLM（惰性导入）。
- `api/assistant.py`：`GET/PUT/DELETE /assistant/providers[/{id}]`、`POST .../test`、
  `GET/POST /assistant/sessions`、`GET/DELETE /assistant/sessions/{id}`、
  `GET /assistant/sessions/{id}/messages`、`POST .../messages`（SSE）、
  `GET /assistant/messages/{id}/transparency`。
- `db/assistant_repo.py`：`assistant_sessions / assistant_messages / assistant_tool_calls`。
  工具调用只存 `{name,args,resultSummary,ok,durationMs}`，不存完整返回值。
- 透明面板：每条 assistant 消息带 `{provider,model,sentFields,redactions,approxTokens,
  recordIds,analysisIds,includeNotes,toolCalls,localOnly}`；`notes` 仅在 `includeNotes=true` 时进入
  `sentFields` 并从 `redactions` 移除。
- 前端：`src/pages/assistant.tsx` + `src/features/assistant/**`（provider 设置、会话列表、流式对话、
  停止生成、预设 chips、简明/详细/医生版、工具追踪可展开原始 JSON、透明 Sheet、可点击引用、
  首次外发隐私确认、无 provider/无分析/网络错误状态、常驻非诊断声明）。feature-local i18n bundle。
- 隐私：远程 provider 首次发送弹出「数据将发送到 X」并提供「仅使用本地 Ollama」；波形/逐搏/成员姓名
  永不进入上下文。

## 验证

- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `pytest backend/tests/assistant -q` → **27 项，26 passed + 1 skipped**（Ollama 可选，需
  `EH_TEST_OLLAMA=1`）；覆盖工具循环事件顺序、SSE 格式、透明面板、越权、DPAPI 往返、key 不入日志、
  会话持久化、超时/取消、工具上限。
- 全量（排除 B3-03 暂不可收集的 reports 目录）：`pytest backend/tests -q -m "not slow"
  --ignore=backend/tests/reports` → **334 passed，exit 0**。
- `npm run build` → pass（tsc 0 error；1175.21 kB / gzip 364.94 kB，>500 kB 提示沿用基线）。
- mock 全链路实测（临时 `EH_DATA_DIR` + 合成记录/分析，真实 uvicorn + 构建产物）：
  「这条记录有什么异常？」→ 3 次工具调用 → 回答含 72.0 bpm / RMSSD 41.5 / 异常 1.70%；
  刷新后会话与透明度仍在；浏览器 console error 0。
- 截图（mock、合成数据）：`reports/screenshots/B3-04-assistant-light.png`、
  `B3-04-assistant-dark.png`、`B3-04-tool-trace.png`、`B3-04-transparency.png`。
- 实测环境注意：本机 16GB 内存被并行 Agent 占满时 `tsc/vite` 会 native OOM；用
  `RAYON_NUM_THREADS=1 UV_THREADPOOL_SIZE=1` 可稳定构建（非代码问题）。

## 未做 / 偏离

- 未连真实 Ollama / OpenAI / Anthropic（本机无对应 key、未确认 Ollama 进程）；适配器与错误脱敏已实现，
  mock 覆盖主路径。`test_ollama_optional.py` 提供开关。
- `approxTokens` 是首轮发送的字节估算（含工具定义），不含后续工具结果；面板已标注「估算」。
- 取消没有独立 API：客户端断开（AbortController）+ 服务端 0.5s 断连探测；落库为 `cancelled` 并回发
  `done{cancelled:true}`。
- 工具返回的大结果会截断到 12k 字符再发给模型，不落库。
- 会话没有分页游标 UI（接口支持 limit/offset）。

## 跨区需求（需要别的 Agent 或指挥官处理）

- **B3-03**：`backend/tests/reports/test_api.py` 与 `backend/tests/modules/test_api.py` 同名，
  全量 pytest 收集失败（import file mismatch）；建议把前者改名 `test_reports_api.py`。
- **共享接线（已做，最小改动）**：`api/__init__.py` 加 `_mount_assistant_router`；
  `db/base.py` 的 `init_db/reset_db` 加 assistant 表 import；`src/pages/coming-soon.tsx` 的占位
  `AssistantPage` 改为 re-export `@/pages/assistant`（App.tsx 无需改动，也不影响 trends/reports）。
- **B3-02**：无冲突；未改 `src/lib/api/**`、`src/lib/i18n/**`、`App.tsx`。

## 需要指挥官决策

- 默认模型名（`gpt-4.1-mini` / `claude-sonnet-5` / `llama3.1`）是否保留为新建 provider 的预填值。
- 是否把 DPAPI 文件升级为 Windows 凭据管理器（当前按提示词要求用 DPAPI 文件）。
- 真实 Ollama 的 tool calling 兼容性需要一次人工实测（不同模型差异较大）。

## 建议下一批

- 真实 Ollama/OpenAI 联调；精确 token 计数（LiteLLM usage）；独立取消 API；会话搜索/导出；
  「引用指南条目」需要先有指南数据源。

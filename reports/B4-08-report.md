# 报告 · B4-08 LLM 真实联调 + 助手收尾

状态：完成（真实 Ollama 已联调；外部 API 无 key，未实测）

## 交付

- `llm/providers.py` 不变；`llm/agent.py`：错误映射改为 401/403/404/408/422/429/5xx/连接失败分类，
  错误文本只含 provider 类型与状态，不含 key 与请求体；流式请求在「首 token 之前」对 429/5xx/网络错误
  自动重试 1 次（已输出后不重试，避免重复 token）；整轮超时 60s→90s（给本地模型冷加载留余量）。
- 用量：Ollama 取 `prompt_eval_count/eval_count`，LiteLLM 走 `stream_options.include_usage`，mock 按字节
  估算并标注 `estimate`；多轮工具循环按轮累加，写入消息 `data.usage`、透明面板与 `done` 事件。
- 取消：新增 `llm/turns.py`（进程内登记表）+ `POST /assistant/messages/{id}/cancel`；SSE 新增 `start`
  事件回传服务端消息 ID，前端停止按钮先调取消 API、5s 未结束再断开连接兜底；进程重启后的残留
  `streaming` 消息直接修正为 `cancelled`。
- 会话：`GET /assistant/sessions?q=` 按标题或**首条用户消息**搜索（LIKE 通配符按字面处理）；
  `PATCH /assistant/sessions/{id}` 重命名（首条消息不再覆盖用户手写标题）；消息分页支持
  `limit/offset/order=asc|desc` 并返回 `total/hasMore`；新增 `GET .../export` 导出 Markdown。
- 导出默认脱敏：只含正文、工具名称/结果摘要、引用 ID、用量；不含工具原始返回、波形、逐搏、备注、
  成员姓名；`includeToolArgs=true` 才带工具参数。文件名 `eclipse-health-assistant-YYYYMMDD-HHMMSS.md`。
- 前端：provider 测试结果展示「延迟 / 模型可用 / 支持工具调用 / 本地模型列表」；无 key 明确提示；
  空状态提供 Mock / Ollama / API Key 三种快速入口；助手消息显示模型、耗时、tokens（含来源）；
  会话搜索、行内重命名、导出、加载更早消息；错误提示可关闭；保留工具追踪、透明面板、引用、预设与风格切换。
- 修复 B3-04 遗留：工具调用 ID 截断为 12 位 UUIDv7（同一毫秒会撞主键，偶发 500）；改为完整 UUID。
- 新测试：`test_provider_probe.py`（错误映射/能力探测/超时/未安装模型）、`test_usage_retry_cancel.py`
  （用量/重试/取消登记表/取消 API/越权）、`test_session_search_export.py`（搜索/重命名/分页/导出）；
  `test_ollama_optional.py` 扩展为可达性、能力探测、真实取消三轮（默认跳过）。

## 验证

- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `pytest backend\tests\assistant -q` → **50 passed, 3 skipped**；连续 25 次运行 0 失败（修复主键冲突后）。
- `EH_TEST_OLLAMA=1 EH_TEST_OLLAMA_MODEL=qwen3:4b pytest ... -m slow` → **3 passed**（Ollama 进程停止后自动 skip）。
- 真实联调（临时 `EH_DATA_DIR` + 合成记录/分析 + 真实 uvicorn 路径）：
  - 能力探测：`ok=true, available=true, supportsTools=true, latencyMs=5148`，模型列表 3 个。
  - 一轮 `list_records` 工具调用 → 回答正确引用记录 ID 与非诊断声明；`first_token=29.1s`、
    `total=30.4s`（qwen3:4b 带思考链）、`usage=2789/1532`、落库 `completed`；导出 Markdown 内容核对通过。
  - `qwen3.5:9b`：本机 4 个 Agent 并行、可用物理内存仅 2.1GB 时 `/api/chat` 返回 500
    （CUDA0/CUDA_Host OOM）；早前内存充足时同一请求 31.7s 成功。属环境限制，非代码错误。
- `npm run build` → pass（tsc 0 error；1,358.80 kB / gzip 417.27 kB，>500kB 提示沿用基线）。
- 截图（mock）：`B4-08-{assistant-light,assistant-dark,tool-trace,transparency,provider-test}.png`；
  Chrome CDP 实测搜索（命中/无结果/恢复）与行内重命名，console error 0。

## Provider 能力矩阵

| provider | 连通 | tool calling | 实测延迟 | 用量来源 |
|---|---|---|---|---|
| mock | 是 | 是（确定性） | ~0 ms | 估算 |
| Ollama qwen3:4b | 是（`/api/tags`） | 是（`/api/show` capabilities） | 5.1s 热 / 24.8s 冷 | provider |
| Ollama qwen3.5:9b | 模型已安装 | 是 | 本机内存不足时 500 | provider |
| Ollama qwen3:4b（关 think） | 是 | **否**（会把推理写进 content） | 13s | provider |
| OpenAI / Anthropic | 未测（无 key） | 由 `litellm.get_supported_openai_params` 判断 | — | provider |

## 未做 / 偏离

- 外部 API 未联调：环境中没有 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY`；
  仅存在 `MINIMAX_API_KEY`，不在本任务允许的 provider 范围内，未写入任何文件或日志。
- Ollama `think` 默认交给模型：实测 qwen3:4b 关闭 think 后不调用工具，因此不默认发 `think:false`；
  UI 未暴露开关（`provider.options.think` 可手工配置，API 未透出）。
- 取消轮次的 SSE `done` 事件不含 usage（agent 异常路径拿不到累计值）；透明面板仍会落库。
- 导出下载用 Blob + `<a download>`；Tauri WebView2 若拦截下载，需要 Tauri 侧保存对话框配合。
- qwen2.5:3b 已下载到 67% 后停止（速度约 0.3 MB/s，qwen3:4b 已验证可用）；如需更快的默认模型可续传。

## 跨区需求（需要别的 Agent 或指挥官处理）

- Qwen 系列建议写进 README/设置页：本机可用的工具调用模型为 `qwen3:4b`（需保留 thinking）或
  `qwen3.5:9b`（内存充足时）；`qwen2.5vl` 不支持工具。
- 如果要把导出保存为文件对话框，需 `src-tauri/**` 的 dialog/fs 权限（B4-01 或收尾统一处理）。
- 提交 `920ae0b` 是其他 Agent 全量 `git add` 时带入的 B4-08 进行中文件；我方未改写历史，后续修正仍在工作区，收尾提交时请一并确认；未改 `src/lib/api/**`、`src/lib/i18n/**`、`App.tsx`。

## 需要指挥官决策

- 新建 Ollama provider 的默认模型是否从 `llama3.1` 改为 `qwen2.5:3b` / `qwen3:4b`（本机实测更稳）。
- 是否在 UI 暴露「关闭思考」开关（更快但部分模型不调工具），以及是否显示 token 成本估算。
- 会话导出是否需要 Tauri 原生保存对话框与「包含工具参数」可见开关。

## 建议下一批

- 用户提供外部 key 后做 OpenAI/Anthropic 真实联调（含 401/429 与流式中断）。
- 会话全文搜索升级 SQLite FTS5；导出 PDF/分享链接；指南引用库需先有数据源。
- 助手页路由懒加载，降低首屏包体（当前主包 1.36 MB）。

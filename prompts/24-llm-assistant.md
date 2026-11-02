# B3-04 · LLM 助手 + 工具调用可视化

> 难度：极难 4/4 · 建议思考强度：**max**（不可用用 xhigh） · 批次：B3 功能
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 本批最复杂：多厂商、流式、工具循环、凭据安全、透明面板、会话历史。先跑通 mock → Ollama → 外部 API，不要一上来接付费 key。

## 1. 必读

- `docs/V3_FEATURE_BACKLOG.md`：F1 工具追踪、F2 透明面板、F3 预设追问、F4 流式引用、F5 风格、F6 会话历史、H3 凭据管理器。
- `docs/DATA_SCHEMA_V1.md`：§4–§7（可发送给 LLM 的最小切片）。
- `docs/INTERNAL_API_V1.md`：§1 记录、§3 分析、§4 数据形状。
- `reports/B2-01-report.md`、`reports/B2-03-report.md`。
- 代码：`backend/src/.../db/base.py`、`db/analysis_repo.py`、`api/analyses.py`、`src/pages/assistant.tsx`、`src/lib/api/client.ts`。

## 2. 环境事实

- 已装：`litellm`、`pydantic-ai`、`httpx`、`sse-starlette`、`sqlmodel`、`pydantic`。
- **没有 pip/uv，不要新增 Python 依赖**；Windows 凭据存储用 **DPAPI + ctypes**（`CryptProtectData`/`CryptUnprotectData`），密文落 `backend/.data/secrets/providers.json`，不落明文。
- 前端已有 TanStack Query/i18n/shadcn；不要新增 UI 依赖。

## 3. 你必须交付

### 后端

1. **Provider 配置与凭据**
   - `llm/providers.py`：provider 记录 `{id, kind: openai|anthropic|ollama|mock, label, baseUrl?, model, keyRef?, enabled}`。
   - 支持的 kind：
     - `openai` / `anthropic`：LiteLLM，`api_key` 从 DPAPI 解出；
     - `ollama`：`http://127.0.0.1:11434`，`/api/chat` 流式；
     - `mock`：确定性回复 + 工具调用，供测试/无 key 演示。
   - API：`GET /assistant/providers`（脱敏，不返回 key）、`PUT /assistant/providers/{id}`、`POST /assistant/providers/{id}/test`、`DELETE`。
   - Key 永不进日志/响应/异常栈；错误信息只显示 provider 类型与 HTTP 状态。
2. **工具（只读、最小切片）**
   - `list_records(limit)`、`get_record(recordId)`、`get_analysis(analysisId)`、`get_measurements(analysisId)`、`get_trends(metrics, days)`（若 B3-02 已实现，读其 API；否则跳过）、`get_model_card()`。
   - 只返回摘要/测量/质量/警告；**不返回原始波形、notes、member 姓名**（除非用户显式允许上下文）。
   - 工具参数校验：recordId/analysisId 必须属于当前成员；越权返回 `NOT_FOUND`。
3. **对话与工具循环**
   - `llm/agent.py`：系统提示（非诊断、引用工具结果、不要编造）、最多 5 次工具调用、超时 60s、可取消。
   - `POST /assistant/sessions/{id}/messages` 返回 **SSE** 流：`token`、`tool_call`、`tool_result`、`citation`、`done`、`error`。
   - 请求体：`{content, style:"brief"|"detailed"|"doctor", providerId, recordId?, includeNotes?:false}`。
   - 上下文：默认只带选中记录的最新分析摘要 + 测量；`includeNotes=true` 时才带 notes，并在透明面板标注。
4. **透明面板数据**
   - 每条 assistant 消息生成 `transparency`：`{provider, model, sentFields, redactions, approxTokens, recordIds, analysisIds}`。
   - `GET /assistant/messages/{id}/transparency`。
   - 工具调用记录：`{name, args, resultSummary, durationMs, ok}`，不存完整返回（避免 PHI 膨胀）。
5. **会话历史（SQLModel on `db/base.Base`）**
   - `assistant_sessions`、`assistant_messages`、`assistant_tool_calls`；注册到 `init_db`（参考 B2-01 的 `analysis_repo` 注册方式）。
   - API：`GET/POST /assistant/sessions`、`GET /assistant/sessions/{id}`、`DELETE`、`GET /assistant/sessions/{id}/messages`。
6. **测试**
   - mock provider：工具循环（list→get analysis→回答）、SSE 事件顺序、透明面板字段、越权记录、key 加密/解密 roundtrip、key 不出现在日志、会话持久化、取消/超时。
   - 不联网；Ollama 测试标记 `slow` 且可跳过。
7. **隐私**
   - 首次使用显示「数据将发送到 X provider」；用户可选择「仅本地 Ollama」；不发送波形/notes；透明面板必须能解释每次发送。

### 前端

8. **助手页**（`src/pages/assistant.tsx` + `src/features/assistant/**`）
   - Provider 设置卡：类型/模型/baseUrl/key（密码框，保存后只显示已配置）、测试连接。
   - 会话列表 + 新建/删除；聊天区流式显示；停止生成。
   - 预设 chips（F3）：「这条有什么异常？」「需要就医吗？」「解释一下 HRV」「和上次比怎么样？」
   - 风格切换（F5）：简明/详细/医生版。
   - 工具调用追踪（F1）：每次调用的名称、参数、耗时、成功/失败，可展开原始 JSON。
   - 透明面板（F2）：「本次发送了什么」——字段、脱敏项、估算 token、记录/分析 ID。
   - 引用（F4）：回答里引用工具结果/记录，显示为可点击 chip。
   - 无 provider / 无分析 / 网络错误的状态齐全；非诊断声明常驻。
9. **i18n / 边界**
   - feature-local bundle：`src/features/assistant/i18n.ts`，`i18n.addResourceBundle`；不改共享 i18n。
   - 只 import 共享 `apiFetch`/类型；不改 `src/lib/api/*`。
   - 截图：`reports/screenshots/B3-04-assistant-light.png`、`B3-04-tool-trace.png`、`B3-04-transparency.png`。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/llm/**
backend/src/eclipse_health_backend/api/assistant.py
backend/src/eclipse_health_backend/db/assistant_repo.py
backend/tests/assistant/**
src/pages/assistant.tsx
src/features/assistant/**
reports/screenshots/B3-04-*.png
```

不要动：`src/lib/api/**`、`src/lib/i18n/**`、`src/App.tsx`、`src/pages/{trends,compare,reports}.tsx`、`src/features/{trends,reports}/**`、`src-tauri/**`、`backend/api/{analyses,records,trends,reports}.py`、`db/base.py` 的结构（如需注册表，按现有模式加 import，报告说明）、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 与其他 Agent 的契约

- B3-02 拥有共享前端层；你只加 feature 目录，不改共享 i18n/client/types。
- B3-02 的趋势 API 可能未就绪：`get_trends` 工具先做能力探测，404 时返回 `unavailable`，不要阻塞主流程。
- 路由 `/assistant` 已存在；只替换页面组件。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant -q
npm run build
# 后端 + dev；用 mock provider 走一轮带工具调用的对话，再试 Ollama（可选）
```

报告写：provider 支持矩阵、工具清单、SSE 事件、透明面板字段、key 存储方式、mock/Ollama 实测、截图、未做项。

## 7. 明确不做

语音朗读（F7 暂不加入）、联网搜索、自动诊断/处方、多模态图片、云端同步、模型微调、付费计费、工具写操作（只能读）、跨成员上下文。

# B4-08 · LLM 真实联调 + 助手收尾

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 2）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：B3-04 的助手已能用 mock；本批把它接到真实 provider（优先 Ollama），补用量/取消/搜索，并把错误处理打磨到可交付。

## 1. 必读

- `reports/B3-04-report.md`（provider/工具/SSE/透明面板/DPAPI）
- `docs/V3_FEATURE_BACKLOG.md`：F1–F6、H3
- `docs/INTERNAL_API_V1.md`：§1/§3/§4（可发送数据）
- 代码：`backend/src/.../llm/**`、`api/assistant.py`、`db/assistant_repo.py`、`src/features/assistant/**`

## 2. 真实联调策略（先探测，不硬装）

1. **Ollama**：`ollama --version` 或 `http://127.0.0.1:11434/api/tags`。
   - 已存在：拉一个**支持 tool calling 的小模型**（如 `qwen2.5:3b` / `llama3.2:3b`，按本机内存选择），跑一轮「工具调用 → 回答」；记录模型名/耗时/失败点。
   - 不存在：**不要系统级安装 Ollama**；用 mock 回归，报告「需要用户安装 Ollama 或提供 API Key」。
2. **外部 API**：仅当环境变量存在（`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY`）时测试；没有就不要编 key。
3. 网络允许（见 `00-COMMON.md` 例外）；下载模型/接口调用要记录来源，不把 key 写进文件/日志。

## 3. 你必须交付

1. **Provider 打磨**
   - 统一超时/重试/错误映射（401/403/429/5xx/连接失败），错误信息不含 key/完整请求。
   - `POST /assistant/providers/{id}/test` 返回模型可用性、延迟、是否支持 tool calling（Ollama 需探测）。
   - 新建 provider 的默认模型名保留（gpt-4.1-mini/claude-sonnet-5/llama3.1），可在 UI 改。
2. **用量与取消**
   - 记录每轮 `usage`（prompt/completion tokens，LiteLLM/Ollama 有则取，没有则 null）；透明面板显示。
   - 独立取消 API 或可靠断连：`POST /assistant/messages/{id}/cancel`（或 SSE 断开 + 0.5s 探测，保留现状并补测试）。
3. **会话**
   - 会话搜索（标题/首条消息）、重命名、删除；消息分页（limit/offset）UI 可用。
   - 导出会话为 Markdown（不含 tool 原始大结果）；导出默认脱敏。
4. **助手前端**
   - Provider 设置：测试连接结果显示 tool calling 支持；无 key 时明确提示。
   - 用量/模型/延迟显示；取消按钮可靠；会话搜索/重命名/导出；错误态可读。
   - 保持现有工具追踪/透明面板/引用/预设 chips/风格切换。
5. **测试**
   - mock 回归全绿；Ollama 可选测试（`EH_TEST_OLLAMA=1`）；错误映射；取消；用量；搜索/导出。
6. **报告** `reports/B4-08-report.md`：provider 能力矩阵（mock/Ollama/external）、实测模型与耗时、需要用户提供什么、未做项。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/llm/**
backend/src/eclipse_health_backend/api/assistant.py
backend/src/eclipse_health_backend/db/assistant_repo.py
backend/tests/assistant/**
src/pages/assistant.tsx
src/features/assistant/**
reports/B4-08-report.md
reports/screenshots/B4-08-*.png
```

不要动：`src/lib/api/**`、`src/lib/i18n/**`、`src/App.tsx`、其他页面/feature、`src-tauri/**`、`backend/{reports,trends,importers,export,privacy,diagnostics,metrics}/**`、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant -q
npm run build
# mock：工具调用/透明面板/取消/导出
# 若本机有 Ollama：拉小模型，跑同一轮工具调用
```

## 6. 明确不做

系统级安装 Ollama、云端账号/计费、联网搜索、语音、自动诊断、指南引用库（未确认）、多模态、模型微调。真实外部 API 无 key 时只报告，不阻塞 mock 交付。

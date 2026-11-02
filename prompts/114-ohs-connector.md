# G5 · 可选 Open Health Sync 连接器（外部服务 + URL/Token）

> 先读 `prompts/00-COMMON.md`、`docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`、OHS 文档（`docs/api.md`、`docs/mcp.md`）。
> **思考强度：low。** 只做「连接 + 测试 + 同步日汇总到健康数据」，不做 OHS 安装/容器管理。
> 普通用户不需要 Docker；内置 Apple/小米导入继续可用。

## 目标

设置页新增「Open Health Sync（可选）」：用户已有 OHS 服务时，填 base URL + token，测试连接并同步数据到本应用健康记录；没有 OHS 的用户完全不受影响。

## OHS 事实（已核实）

- OHS 是 Go + Postgres + Docker 的独立服务；REST base 默认 `http://localhost:8080`。
- 认证：`Authorization: Bearer <tenant key | user token>`；用户 token 可只读、最长 30 天。
- 关键读接口：`/v1/users`、`/v1/users/{id}/samples`、`/sleep`、`/workouts`、`/daily`（见 OHS docs/api.md）。
- MCP：`/mcp`（Streamable HTTP）或 `ohs mcp`；本项目已有自己的 MCP，不需要代理 OHS。
- AGPL-3.0：只通过 HTTP 调用，不复制其代码。

## 交付

### 1. 后端连接与存储

- 新建 `backend/src/eclipse_health_backend/ohs/`：
  - `client.py`：httpx 客户端，base URL（仅 http/https、默认 `http://127.0.0.1:8080`）、token；`test_connection()` 调 `GET /openapi.yaml` 或 `GET /v1/users`（按 token 类型）；超时 10s。
  - `store.py`：保存 base URL + token；token 用 Windows DPAPI（`win32crypt`）加密；不可用时明确报错并拒绝保存明文。文件放 `<EH_DATA_DIR>/ohs.json`。
  - `sync.py`：
    - 选择用户：tenant key 时 `GET /v1/users`，取第一个/指定 `user_id`；user token 可直接用。
    - 同步最近 30 天 `GET /v1/users/{id}/daily`（或 samples）中的步数、静息心率、睡眠时长、体重、血压（按 OHS 实际字段；字段不确定时写 `warnings`，不要猜错）。
    - 写入本应用健康记录（复用 B4 的 `org.eclipsehealth.health.*` 格式），用 OHS 记录 id/日期做 `externalId` 去重。
    - 返回 `{created,skipped,failed,warnings[]}`；单条失败不回滚已写入。
  - `api.py`：`GET/PUT /api/v1/ohs/settings`、`POST /api/v1/ohs/test`、`POST /api/v1/ohs/sync`；**不要改 `api/__init__.py`**（指挥官挂载）。
- 测试：mock httpx（不连真实 OHS）；settings 加密/不可用、test 成功/401、sync 去重/失败计数、无 token 拒绝。

### 2. 设置页 UI

- `src/pages/settings.tsx` 新增「Open Health Sync（可选）」面板（放在外部访问附近）：
  - 说明「需要你自己运行 OHS（Docker/Postgres）；普通用户无需安装，内置 Apple/小米导入照常可用」；
  - base URL、token 输入（password）、保存、测试连接、同步按钮；显示最近同步结果/警告；
  - 连接示例/文档链接；未配置时隐藏同步按钮；
  - 文案 `settings.ohs.*`（zh-CN/en-US）。
- 不在启动时自动连接；只有用户点击测试/同步才请求。

### 3. 文档

- 新建 `docs/INTEGRATIONS/OPEN_HEALTH_SYNC.md`：OHS 快速启动（Docker Compose）、创建 token、本应用配置、同步范围/字段映射、限制（OHS 未运行/字段变化）、AGPL 说明。
- 不改 `docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md` 的主体（可加一行指向新文档）。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/ohs/**`（新建）
- `backend/tests/ohs/**`（新建）
- `src/pages/settings.tsx`
- `src/features/external-access/**` 只读，不修改
- `src/lib/i18n/**`（只新增 `settings.ohs.*`）
- `docs/INTEGRATIONS/OPEN_HEALTH_SYNC.md`（新建）
- `reports/G5-*.md`、`reports/screenshots/G5-*.png`

## 明确不做

- 不安装/管理 Docker/Postgres；不打包 OHS；不复制 OHS 代码。
- 不改内置导入器、不改评分/教练；不新增依赖（httpx/pywin32 已装）。
- 不改 `api/__init__.py`；不 commit；不改 `prompts/`、`uploads/`。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\ohs -q
npm run build
```

报告 `reports/G5-ohs-report.md`，≤80 行：配置/加密、测试连接、同步字段与去重、真实测试输出、未验证项。

# C2 · Stage C 端到端验收（真实安装 → 卡片/工具/页面 → 卸载）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md`、`reports/B1`–`B5`，再读本文件。
> **只做验收脚本与报告，不改生产代码。**

## 目标

用真实后端 + 真实模块安装流程，验证 Stage A/B 的平台能力端到端可用：

1. 安装一个同时带 `ui.widgets`、`tools`、`ui.pages` 的测试模块；
2. 首页出现卡片；助手工具表出现该工具；模块页可打开并提交表单；
3. 禁用模块 → 三处同时消失；重新启用 → 恢复；卸载 → 不残留。

## 交付

### 1. 测试模块

- 新建 `backend/tests/fixtures/modules/e2e/`：
  - `module.json`：`type="health-domain"`，声明 `ui.widgets`（stat + list）、`tools`（一个 echo/计数工具）、`ui.pages`（text + form + table），权限 `records:read`、`llm`；
  - `src/main.py`：stdio JSON-RPC worker，支持 `health`、widget 数据方法、tool 方法、page 数据/提交方法；只返回固定测试数据，不写真实记录。
- 用现有 `modules.package.pack_directory` 打成 `.ehmod`（脚本内临时目录，不提交包）。

### 2. 验收脚本

- 新建 `scripts/e2e_stage_c.py`：
  - 用临时 `EH_DATA_DIR` 启动后端（端口 8790），等待 `/api/v1/health`；
  - 安装测试模块 → 授权 `records:read`、`llm` → 启用/启动；
  - 断言 `GET /modules/contributions` 三类都有该模块；
  - 调用 `POST /modules/{id}/rpc` 执行 tool/widget/page 方法，断言结果；
  - 调用页面表单对应的 submit 方法，断言写入/返回值；
  - 禁用模块 → contributions 不再包含；启用 → 恢复；卸载 → 目录消失；
  - 清理临时数据目录与进程；失败时打印明确原因并退出非 0。
- 可选：用 Playwright 打开真实前端（Vite preview）截图首页/助手/模块页；若环境不允许，至少用 API 证据 + 一张模块页截图。

### 3. 报告

- `reports/C2-e2e-report.md`（≤80 行）：每一步的真实命令/输出、通过/失败、截图路径、发现的跨区问题（不要修）。
- 截图放 `reports/screenshots/C2-*.png`。

## 文件所有权（只改这些）

- `backend/tests/fixtures/modules/e2e/**`（新建）
- `scripts/e2e_stage_c.py`（新建）
- `reports/C2-e2e-report.md`、`reports/screenshots/C2-*.png`

## 明确不做

- 不改生产代码（`backend/src/**`、`src/**`、`schemas/**`）；发现问题写「跨区需求」。
- 不提交 `.ehmod` 包、不写 `uploads/`、不改 `prompts/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe scripts\e2e_stage_c.py
```

脚本必须可重复运行（每次临时数据目录、随机端口或固定 8790 前先清理）。

## 报告要点

- 模块安装/授权/启用/禁用/卸载每一步是否成功；
- contributions 三类是否随状态变化；
- tool/page RPC 的真实返回；
- 发现的阻塞项（例如 schema 拒绝、query 不刷新、页面路由问题），按「文件:行为」写清。

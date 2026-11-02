# F4 · 对外 API 设置页：API Key 管理 + 连接示例

> 先读 `prompts/00-COMMON.md`、`docs/EXTERNAL_API.md`（F3 产出；若还没生成，按本文件契约）、`src/pages/settings.tsx`、`src/features/modules/api.ts` 的 fetch 写法。

## 目标

在设置页提供「外部访问」区域：创建/撤销 API Key、选择权限、复制 MCP/REST/OpenAI 连接示例。**仅本机**，不做 LAN/公网。

## 后端契约（F3 实现，前端按此对接）

- `GET /api/v1/external/keys` → `{items:[{id,name,prefix,scopes,createdAt,lastUsedAt,revokedAt}]}`
- `POST /api/v1/external/keys` `{name, scopes:["read"|"write"|"assistant"]}` → `{id,name,token,prefix,scopes,createdAt}`（token 仅此一次）
- `DELETE /api/v1/external/keys/{id}` → 204
- 外部 base：`http://127.0.0.1:8765/api/v1/external`
- OpenAI base：`http://127.0.0.1:8765/api/v1/external/openai/v1`，模型 `eclipse-health`
- MCP：`python -m eclipse_health_backend.mcp_server`，环境变量 `EH_EXTERNAL_KEY`、`EH_API_BASE`

## 交付

### 1. 数据层

- 新建 `src/features/external-access/api.ts`：本地 fetch（用 `baseUrl`），类型本地定义；错误用 `ApiError`/普通 Error；后端 404 时返回 `unavailable` 状态，不崩溃。
- 新建 `src/features/external-access/types.ts`。

### 2. UI

- 新建 `src/features/external-access/external-access-panel.tsx`，在 `src/pages/settings.tsx` 的合适位置挂载（建议桌面/诊断附近）。
- 面板内容：
  - 标题「外部访问」+ 说明「仅本机；API Key 只显示一次；可随时撤销」。
  - 「创建 Key」按钮 → Dialog：名称（必填，≤64）、权限复选框：
    - 读取记录/分析/健康数据（read）
    - 写入健康数据（write）
    - 调用应用内 Agent（assistant）
    - 默认勾选 read+write。
  - 创建成功后 Dialog 切换为「复制 Key」：显示完整 token、复制按钮、警告「关闭后无法再次查看」；关闭后刷新列表。
  - Key 列表：名称、`prefix…`、scopes 徽标、创建时间、最后使用、撤销（两段式确认）；已撤销的灰显。
  - 空状态：说明先创建 Key，再配置外部 Agent。
  - 连接示例卡片（每个带复制按钮）：
    - MCP：命令 + `EH_EXTERNAL_KEY` 示例（用 `****` 占位，不自动填真实 key）；
    - REST：`curl` 列记录示例；
    - OpenAI：base URL + model + Python/curl 示例。
  - 外部访问关闭/后端不可用：显示「后端未启用外部访问」+ 重试，不报红屏。
- 文案全部走 `src/lib/i18n/**` 的 `settings.external.*`（zh-CN/en-US）；不覆盖 F2 的 palette/dashboard.quote 键。

### 3. 验证

- `npm run build` 通过。
- 用 mock/拦截（Playwright CDP）验证：空状态、创建 key、token 只显示一次、复制、撤销、404 降级；亮/暗截图 `reports/screenshots/F4-*.png`；控制台 0 error。
- 若后端 F3 已完成，用真实后端再走一遍创建/列表/撤销。

## 文件所有权（只改这些）

- `src/features/external-access/**`（新建）
- `src/pages/settings.tsx`
- `src/lib/i18n/**`（只新增 `settings.external.*`）
- `reports/F4-*.md`、`reports/screenshots/F4-*.png`

## 明确不做

- 不改后端（F3）、不改 themes/quotes/branding/layout。
- 不做 LAN/二维码/OAuth；不做 key 明文再次查看。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

报告 `reports/F4-external-access-ui-report.md`，≤80 行：UI 结构、创建/撤销流程、token 一次性、404 降级、截图、未做项。

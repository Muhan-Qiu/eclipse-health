# 报告 · F4 对外 API 设置页：API Key 管理 + 连接示例
状态：完成

## 交付
- `src/features/external-access/types.ts`：`ExternalKey` / `CreatedExternalKey` / scope 类型与 `ExternalKeysState`（ok / unavailable）。
- `src/features/external-access/api.ts`：`listExternalKeys` / `createExternalKey` / `revokeExternalKey`，本地 fetch、`ApiError`；404 与网络失败返回 `unavailable`，非 404 抛出。
- `src/features/external-access/external-access-panel.tsx`：设置页「外部访问」面板。
  - 创建对话框：名称（必填、≤64）、read/write/assistant 复选框，默认 read+write；提交前校验名称与至少一项权限。
  - 创建成功后对话框切换为「复制 Key」：完整 token、复制按钮、「关闭后无法再次查看」警告；关闭后清空 token 并刷新列表。
  - Key 列表：名称、`prefix…`、scope 徽标、创建时间、最后使用、两段式撤销；已撤销灰显 + 删除线 + 「已撤销」徽标，不再显示撤销按钮。
  - 空状态、加载中、`后端未启用外部访问` + 重试；不可用时禁用「创建 Key」。
  - 三张连接示例卡（MCP / REST / OpenAI 兼容），均带复制按钮，key 用 `****` 占位。
- `src/pages/settings.tsx`：在桌面与诊断之间挂载 `ExternalAccessPanel`（`desk:col-span-8 xl:col-span-6`）。
- `src/lib/i18n/zh-CN.ts`、`en-US.ts`：仅新增 `settings.external.*`，未改 palette / dashboard.quote 等 F2 键。

## 验证
- 命令：`npm run build`
- 结果：pass，3.07s，2854 modules；`tsc` 无错误。此前一次构建因类型收窄误用字符串比较报错，已修正（`keysState !== "loading" && keysState.status === "unavailable"`）。
- Playwright（Chrome headless，mock 拦截 `/api/v1/external/keys**`）：
  - 空状态、创建（名称 + assistant 权限）、token 对话框、关闭后列表刷新：pass。
  - token 一次性：关闭后页面与新开创建框中均不含 token，且不再出现「复制 Key」视图：pass。
  - 复制：`navigator.clipboard.readText()` 与完整 token 一致；示例卡复制含 MCP 命令：pass。
  - 撤销：两段式确认 → `已撤销` 徽标、名称删除线、按钮消失：pass。
  - 亮/暗截图与 404 降级：pass；正常流程控制台 0 error，404 场景仅 1 条预期的网络 404 日志，无 JS 异常。
- 真实后端（F3 源码已完成，临时实例 `127.0.0.1:8799`，`EH_DATA_DIR` 指向临时目录）：
  - 创建（read+write+assistant）→ token 以 `eh_ext_` 开头、复制成功、列表不含 token：pass。
  - 带 Bearer 调用 `/api/v1/external/records` 返回 200；关闭对话框后列表显示 Key：pass。
  - 撤销后 `revokedAt` 非空、同一 token 调用 records 返回 401：pass；控制台 0 error。

## 截图
- Mock：`reports/screenshots/F4-empty-light.png`、`F4-create-dialog-light.png`、`F4-token-once-light.png`、`F4-list-light.png`、`F4-revoked-light.png`、`F4-list-dark.png`、`F4-create-dialog-dark.png`、`F4-unavailable-light.png`。
- 真实后端：`F4-real-empty-light.png`、`F4-real-list-light.png`、`F4-real-revoked-light.png`（临时 8799 实例，示例中的 base URL 为 8799）。

## 未做 / 偏离
- 名称上限按提示词取 64；后端 F3 实际允许 80（前端更严格，不冲突）。
- `docs/EXTERNAL_API.md` 尚未生成，接口以提示词契约 + 实际 `backend/.../api/external.py` 为准；MCP 的 `EH_API_BASE` 用 `http://127.0.0.1:8765/api/v1`（与 `mcp_server.py` 默认一致）。
- 未测试真实 OpenAI 流式响应（需要已配置 LLM Provider），仅验证 UI 示例与创建/撤销链路。
- 未做 LAN / 二维码 / OAuth / token 明文再次查看，符合范围。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 当前 8765 上运行的后端进程尚未加载 F3 路由（仍返回 404）；需重启后端才能让本机设置页直连真实接口。
- `docs/EXTERNAL_API.md` 建议由 F3 补齐，前端示例已与其源码路径对齐。
- 并行 `npm run build` 会在 `dist/assets` 留下多份旧的 `settings-*.js` / `i18n-*.js`，不影响本轮验收，但发布前建议串行构建。

## 需要指挥官决策
- 无。

## 建议下一批
- 在 key 列表显示「最后使用」的自动刷新；外部调用审计入口（复用模块审计页）。
- 真实 LLM 配置后的 OpenAI 兼容端点端到端联调（含 stream）。

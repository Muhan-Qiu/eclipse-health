# 提示词索引 · Stage E（用户反馈 + 对外 API）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`。
> 当前批次：Stage E，4 个 Agent 并行。D3 已验收（`6410c97`），最终包 `0.1.0` 已构建。
> 用户第二轮反馈见 `docs/USER_FEEDBACK.md`「已收到（2026-10-31 第二轮）」。

## 本轮（Stage E，4 个并行）

| 提示词 | 任务 | 难度 | 思考强度 | 报告 |
|---|---|---|---|---|
| `100-brand-motion-fix.md` | 开屏线性 + 深绿涟漪 logo + 新图标 + 导航淡入淡出 + 删副标题 | 困难 3/4 | high | `reports/F1-brand-motion-report.md` |
| `101-themes-quotes.md` | 3 高饱和 + 2 玻璃主题 + 30 句每日名言 | 困难 3/4 | high | `reports/F2-themes-quotes-report.md` |
| `102-external-api-backend.md` | 对外 API：Key + REST + OpenAI 兼容 + MCP | 困难 3/4 | high | `reports/F3-external-api-report.md` |
| `103-external-access-ui.md` | 设置页外部访问 Key 管理 + 连接示例 | 中等 2/4 | high | `reports/F4-external-access-ui-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/100-brand-motion-fix.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/F1-brand-motion-report.md。
```

其余三份同理替换文件名/报告名。

## 文件所有权冲突预防

- F1：`branding/**`、`components/common/eclipse-mark.tsx`、`components/layout/**`、`lib/motion.ts`、`src-tauri/icons/**`、settings 的 About 文案。
- F2：`lib/theme.tsx`、`lib/palettes.ts`、`index.css`、`lib/quotes.ts`、`dashboard.tsx`、i18n 的 palette/dashboard.quote 键。
- F3：后端 `api/external.py`、`external_auth.py`、`mcp_server.py`、`db/models.py`、`db/base.py`、`api/__init__.py`、`tests/external/**`、`docs/EXTERNAL_API.md`。
- F4：`features/external-access/**`、`pages/settings.tsx`、i18n 的 `settings.external.*`。
- F2/F4 都碰 i18n：只新增自己的键，不重写文件。
- 不要同时跑 `tauri build`/PyInstaller；本轮结束后指挥官统一重打包。

## 已知边界

1. 导航**只淡入淡出**；不做斜向 sweep，不覆盖侧栏，不出现空白白页。
2. 图标用应用内深绿涟漪，不要金/黑。
3. 对外 API **仅本机**；key 只显示一次、存 hash、可撤销；默认 read+write + assistant。
4. OpenAI 兼容端点复用应用内 LLM；无 provider → 503。
5. 名言只用可核实句子；中英双语带作者。
6. 玻璃主题需提供无 `backdrop-filter` 的回退。

## 收尾

四份报告齐后：指挥官全量 `pytest` + `ruff` + `npm run build`，处理跨区冲突，重打 NSIS，更新 release notes/校验和，交用户验收。

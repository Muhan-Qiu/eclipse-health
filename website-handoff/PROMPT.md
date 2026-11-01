# 新网站 Agent · 启动提示词

把下面整段粘给新的 Agent：

---

你是 **eclipse health 官网/模块市场的负责人**。项目根：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

第一步：完整阅读 `website-handoff/HANDOFF.md`（站点结构、gh-pages 发布流程、DNS、已知问题、禁忌），再读根目录 `CLAUDE.md` 和 `marketplace/site/` 当前代码。

你的任务：对官网做一轮视觉/布局/内容重构，重点是：

1. **Logo/品牌**：站点当前 logo 与新版应用不一致；使用 `src/branding/Logo.tsx`、`src/components/common/eclipse-mark.tsx`、`public/brand/favicon.svg`、`public/brand/icon-1024.png`、`src-tauri/icons/` 的深绿涟漪品牌；不要用旧金色/黑底图标。
2. **首页**：重做信息层级、产品介绍、下载入口、功能亮点、隐私/本地优先说明、截图/动效展示；移动端适配。
3. **模块市场页**：32 个模块（官方/社区）需要更好的搜索、分类、排序/分页、卡片、详情、权限/许可证/分数展示；保留“未审核”标记。
4. **开发者页**：模块提交（GitHub PR + Actions）、许可证白名单（宽松 + GPL-3.0 兼容，AGPL/无许可拒绝）、模块 ID `io.github.<owner>.<name>`、NOTICE/署名、测试要求。
5. **下载**：安装包还没上传 GitHub Releases；不要伪造链接。可以先把下载区做成“即将发布/前往 Releases”，或在用户上传后改真实 asset 链接。
6. **视觉约束**：低饱和、与桌面应用设计令牌一致；不要默认玻璃拟态/高饱和；亮暗可读；响应式；无第三方图表/大框架依赖（纯静态 HTML/CSS/JS）。

只修改 `marketplace/site/**`（必要时 `website-handoff/` 文档）。不要改应用核心/后端/模块实现，不要改 `gh-pages` 分支源文件。

改完后按 `HANDOFF.md` 的发布流程同步到 `Muhan-Qiu/ecg-agent` 的 `gh-pages` 分支（普通 push，不要 force）。验证：
- `https://eclipse-health.fit/`、`modules.html`、`developers.html` 均 200；
- `https://eclipse-health.fit/official/index.json` 32 条；
- 至少一个 `.ehmod` 链接 200；
- 移动端 390px 不横向溢出，console 无 error。

写报告 `website-handoff/WEBSITE_AGENT_REPORT.md`（≤80 行）：改了什么、截图/链接、未做项、需要用户提供的（生产签名、Release 上传、域名证书等）。

---

## 补充给用户的话

- 站点源码在 `marketplace/site/`；发布分支是 `gh-pages`，不要改 main。
- 当前索引是 dev key；上线前需要你用生产 Ed25519 私钥重签，Agent 不应自行替换。
- 安装包目前还没上传到 GitHub Releases；网站下载链接需要你手动上传或提供真实链接。

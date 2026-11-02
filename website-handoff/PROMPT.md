# 新网站 Agent · 启动提示词

把下面整段粘给新的 Agent：

---

你是 **eclipse health 官网/模块市场的负责人**。项目根：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

第一步：完整阅读 `website-handoff/HANDOFF.md`（站点结构、gh-pages 发布流程、已知问题、禁忌），再读根目录 `CLAUDE.md`、`marketplace/site/` 当前代码，以及 `module-copy.zh.json` / `module-copy.en.json`。

当前状态（2026-11-01）：

1. **双语**：根目录是中文，`en/` 是英文；页头有语言切换，页面带 hreflang。改文案时两边都要改。
2. **Logo 暂缓**：用户明确说真正的 logo 还没定，**不要改 logo 与图标**；等品牌定稿后再统一替换。
3. **模块文案**：`module-copy.{zh,en}.json` 按模块 ID 覆盖名称、一句话说明、功能清单、输入输出、适用场景与限制；卡片优先展示功能，详情页再展开权限、依赖、扫描与技术说明。
4. **自研模块**：`relay-ecg` 显示名为「ECG 心搏分析」，`relay-sleep` 为「睡眠分期分析」；模块 ID 保持不变。改名称/简介后要重跑 `scripts/pack_official_modules.py` 与 `scripts/build_marketplace_index.py`。
5. **下载**：首页按钮直接指向安装包资产 `https://github.com/Muhan-Qiu/eclipse-health/releases/download/v0.1.0-alpha/eclipse-health_0.1.0_x64-setup.exe`，点击即下载、不跳转 Release 页面；`v0.1.0-alpha` 安装包已上传，页面标注「已发布」；不要伪造 asset 链接。
6. **视觉**：低饱和、与桌面应用设计令牌一致；不要默认玻璃拟态/高饱和；亮暗可读；响应式；纯静态 HTML/CSS/JS，无第三方框架。

你的任务：按用户后续提出的布局、功能与 GitHub 相关改动继续迭代。只修改 `marketplace/site/**`、`modules/official/*/module.json` 的展示字段（改完重打包重签）与 `website-handoff/` 文档；不要改应用核心、后端或模块实现。

改完后按 `HANDOFF.md` 的发布流程同步到 `Muhan-Qiu/eclipse-health` 的 `gh-pages` 分支（普通 push，不要 force）。验证：

- `https://eclipse-health.fit/`、`modules.html`、`developers.html` 均 200；
- `https://eclipse-health.fit/en/` 及 `en/` 下三页均 200；
- `https://eclipse-health.fit/official/index.json` 10 条、`community/index.json` 22 条；
- `module-copy.zh.json` / `module-copy.en.json` 200；
- 至少一个 `.ehmod` 链接 200；
- 移动端 375/390px 不横向溢出，console 无 error。

写报告 `website-handoff/WEBSITE_AGENT_REPORT.md`（≤80 行）：改了什么、截图/链接、未做项、需要用户提供的（生产签名、Release 上传等）。

---

## 补充给用户的话

- 站点源码在 `marketplace/site/`；发布分支是 `gh-pages`，不要改 main。
- 当前索引是 dev key；上线前需要你用生产 Ed25519 私钥重签，Agent 不应自行替换。
- 安装包已上传到 GitHub Releases（`v0.1.0-alpha`）；新构建替换 asset 后同步更新页面文案。
- Logo 等品牌定稿后再改，本轮未动。

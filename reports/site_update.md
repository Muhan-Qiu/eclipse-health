# A4 · 官网同步 + 模块文档 + 自定义模块提示词

日期：2026-11-02
分支：`feat/ui-alignment`（站点源码 `marketplace/site/`）
发布：`Muhan-Qiu/ecg-agent` → 已重命名 **`Muhan-Qiu/eclipse-health`** 的 `gh-pages`，普通 push
提交：`21168d2`（主体）→ `ce9e58b`（仓库链接改为新名）

## 发布快照

| 项 | 值 |
|---|---|
| 官方索引 | 10 条 |
| 社区索引 | 22 条 |
| 索引生成时间 | `2026-11-01T15:44:44Z`（dev-2026 签名） |
| 模块文案 | `module-copy.zh/en.json` 各 32 条，与两份索引 ID 一一对应，无缺失、无多余 |
| `.ehmod` | official 10 个、community 22 个，均按索引 `file` 字段放到对应目录 |

说明：A2 的拆分索引在本轮发布期间仍在更新（15:19 → 15:35 → 15:44）。网站直接读取同源索引，条数随索引变化；本轮发布的是 `15:44:44Z` 快照。若 A2 之后再重签索引，只需覆盖两份 `index.json` 与新增 `.ehmod` 再推送，不需要改页面。

## 改动

### 1. 官方/社区同步

- 市场页与首页文案改为：官方 = 第一方 + 已验证第三方适配，第一方始终排最前；社区 = 未人工审核、仅自动扫描。
- 市场页两个标签实时显示索引条数（如「官方索引 · 10」「社区索引 · 22」），与应用读同一份索引。
- 社区卡片继续显示「未审核」；第一方卡片显示「官方自研」，排序为官方自研 → 已验证 → 本地化名称。
- 名称、tagline、功能、输入输出等继续由 `module-copy.{zh,en}.json` 覆盖，32/32 覆盖。

### 2. 布局与等高校正

- `styles.css`：
  - 首页 hero 由垂直居中改为顶部对齐，桌面端左右两栏顶边一致。
  - `grid-3 / grid-4 / spotlight-grid / module-grid` 改为显式断点（1 → 2 → 3/4 列），消除 860–1000px 之间的孤儿列；行内卡片由 grid stretch 保持等高。
  - 模块卡片、开发者双栏、下载卡、提示词表单补 `min-width: 0`、`overflow-wrap` 与可换行的 badge，长 ID/许可证/依赖不再撑破网格。
  - 模块详情弹窗、权限行、代码块维持自身滚动，不产生页面横向溢出。
- 实测 375 / 390 / 768 / 1280 四档，六个页面（中英首页/市场/开发者）横向溢出均为 **0**；同一行模块卡片高度差为 **0**；1280 下 hero 两栏顶边差为 **0**、开发者双栏顶边差为 **0**。

### 3. 模块文档下载（开发者页）

新增「模块文档下载」区块与目录项，四个文件同源直链，`download` 属性直接下载，不跳 GitHub：

| 文件 | 语言 | 面向 |
|---|---|---|
| `docs/modules-user-guide.zh.md` | 中文 | 用户：模块能做什么、安装、权限、让 AI 帮你做 |
| `docs/modules-user-guide.en.md` | English | 同上 |
| `docs/modules-agent-guide.zh.md` | 中文 | Agent/开发者：契约 v2、`.ehmod`、`module.json`、stdio JSON-RPC、权限、测试、打包、PR |
| `docs/modules-agent-guide.en.md` | English | 同上 |

Agent 版包含可直接改用的 worker、测试与打包脚本。另加 `.nojekyll`，确保 GitHub Pages 原样返回 `.md`。

### 4. 「没有你想要的模块？」提示词生成器

市场页（中英）新增表单：模块名称、用途、输入、输出、需要的数据/权限。

- 纯浏览器生成，不上传内容；
- 中英两套模板，跟随当前页面语言；
- 生成内容包含需求、契约约束、交付清单与参考链接；
- 支持复制、下载 `.md`、下载 `.txt`，文件名分别为
  `eclipse-health-module-prompt.zh.md/.txt` 与 `.en.md/.txt`；
- 首页 CTA 与开发者页均加入口。

### 5. 顺带修正

- `.ehmod` 下载地址改为相对索引所在目录解析（`/official/modules/…`、`/community/modules/…`）。原逻辑可能拼到上游 GitHub Releases 或根目录 `modules/`，会 404。
- 仓库已重命名为 `Muhan-Qiu/eclipse-health`，站点内 22 处仓库链接已改为新名；旧名 `ecg-agent` 仍会被 GitHub 重定向。

## 线上验证

| URL | 结果 |
|---|---|
| `https://eclipse-health.fit/` | 200 |
| `https://eclipse-health.fit/en/` | 200 |
| `https://eclipse-health.fit/modules.html` | 200 |
| `https://eclipse-health.fit/en/modules.html` | 200 |
| `https://eclipse-health.fit/developers.html` | 200 |
| `https://eclipse-health.fit/en/developers.html` | 200 |
| `https://eclipse-health.fit/official/index.json` | 200 · 10 条 · 与本地内容一致（仅 CRLF/LF 差异） |
| `https://eclipse-health.fit/community/index.json` | 200 · 22 条 |
| `https://eclipse-health.fit/module-copy.zh.json` / `.en.json` | 200 |
| `/docs/modules-user-guide.zh.md` / `.en.md` | 200 · `text/markdown` |
| `/docs/modules-agent-guide.zh.md` / `.en.md` | 200 · `text/markdown` |
| `/official/modules/org.eclipsehealth.relay-ecg-0.1.0.ehmod` | 200 |
| `/community/modules/io.github.grubersjoe.activity-calendar-0.1.0.ehmod` | 200 |

线上页面已确认包含提示词生成器与四个文档入口；语言切换、主题切换、搜索与详情继续可用。

## 截图

- `reports/site-update-modules-1280.png`
- `reports/site-update-developers-1280.png`
- `reports/site-update-home-375.png`
- `reports/site-update-prompt-375.png`

## 未做 / 需要注意

- 未改 logo、未改应用代码、未伪造 Release 或签名状态。
- 索引仍是 `dev-2026`；生产 Ed25519 重签与应用内置公钥更新仍待用户完成。
- GitHub Releases 仍无安装包，下载入口如实标注「安装包待上传」。
- 发布期间 A2 仍在重签索引；若之后索引又变，需再同步两份 `index.json` 与 `.ehmod`。

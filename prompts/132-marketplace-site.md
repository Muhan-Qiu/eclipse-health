# H10 · 模块市场静态站 + 开发者提交/发布流程

> 先读 `prompts/00-COMMON.md`、`docs/REGISTRY_AND_SCANNING_V1.md`、H8 的 `marketplace/README.md` 契约、`docs/MODULE_CANDIDATES_30.md`。
> **思考强度：low。** 只做静态站与文档/CI 模板，不部署。

## 目标

给 GitHub Pages（或任意静态托管）一套可用的市场/下载/开发者页面，以及开发者通过 **GitHub PR + Actions** 提交模块的模板。域名后续 CNAME 即可。

## 交付

- `marketplace/site/`：
  - `index.html`：软件下载（GitHub Releases 链接占位）、模块市场入口、开发者入口；
  - `modules.html`：读取 `../official/index.json` + `../community/index.json`，搜索/分类/详情；无数据时友好提示；
  - `developers.html`：模块开发文档（契约 v2、manifest 示例、权限、依赖、测试、提交 PR 步骤、许可证/署名要求）；
  - `styles.css`、`app.js`：纯静态，无第三方框架；低饱和、响应式、亮/暗自动。
- `.github/`：
  - `workflows/validate-module.yml`：PR 时校验 `module.json`（schema）、打包、路径安全、许可证白名单（拒绝 AGPL/无许可）、NOTICE 存在、`.ehmod` 可解包；失败阻止合并；
  - `workflows/publish-marketplace.yml`：main 分支变更时生成/更新索引（调用 `scripts/build_marketplace_index.py`），不自动签名生产钥（签名由维护者离线完成）；
  - `PULL_REQUEST_TEMPLATE/module.md`：作者、许可证、上游、权限、测试、截图、非诊断声明。
- `docs/MARKETPLACE_GUIDE.md`：域名/CNAME、GitHub Pages 设置、Releases 上传 `.ehmod`、签名流程、官方 vs 社区、下架/撤回、版权/DMCA、安全边界。
- `marketplace/CONTRIBUTING.md`：开发者提交清单（ID `io.github.owner.name`、LICENSE/NOTICE、依赖、测试、权限最小化、非诊断）。

## 文件所有权（只改这些）

- `marketplace/site/**`（新建）
- `marketplace/CONTRIBUTING.md`（新建）
- `.github/**`（新建）
- `docs/MARKETPLACE_GUIDE.md`（新建）
- `reports/H10-marketplace-site-report.md`

## 明确不做

- 不部署、不买域名、不建 GitHub 仓库；不改后端/应用 UI。
- 不做上传后端/账号系统；开发者身份用 GitHub。
- 不复制第三方站点模板/素材；不新增依赖；不 commit。

## 验收

- 用本地静态服务器打开 `marketplace/site/index.html`、`modules.html`、`developers.html`，无 console error；移动宽度不横向溢出。
- `python -m json.tool` 校验 CI 模板中的示例 JSON（如有）。
- 报告 `reports/H10-marketplace-site-report.md`，≤80 行。

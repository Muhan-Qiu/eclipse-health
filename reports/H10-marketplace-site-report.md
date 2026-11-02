# 报告 · H10 模块市场静态站与开发者提交流程

状态：完成

## 交付

- `marketplace/site/`：`index.html` 下载/市场/开发者入口（Releases 占位链接）；`modules.html` 读取 `../official/index.json` 与 `../community/index.json`，支持官方/社区切换、搜索、分类、详情弹窗、权限解释、扫描等级、撤回/未审核标记与空/错误状态；`developers.html` 契约 v2、包结构、manifest 示例、权限、依赖、测试、PR、许可证、非诊断声明；`styles.css` + `app.js` 纯静态、无第三方依赖、莫奈低饱和、亮/暗自动与手动切换、响应式。
- `.github/workflows/validate-module.yml`：PR 校验 schema、ID 命名空间、许可证白名单（拒 AGPL/无许可）、LICENSE/NOTICE、路径安全、密钥模式、打包并解包校验 checksums；失败阻止合并；产物 `dist-ci/`。
- `.github/workflows/publish-marketplace.yml`：main 变更调用 `scripts/build_marketplace_index.py`（缺失时用 `.github/scripts/build_marketplace_index.py` 兜底），dist 缺失时先用 stdlib packer 打包；CI 不接触生产私钥；默认只构建/上传产物，`MARKETPLACE_PUBLISH=true` 才部署 Pages。
- `.github/scripts/`：`validate_module.py`、`build_marketplace_index.py`、`pack_official_modules.py`（stdlib，不改源码树）。
- `.github/PULL_REQUEST_TEMPLATE/module.md`：作者、许可证、上游、权限、测试、截图、非诊断声明。
- `docs/MARKETPLACE_GUIDE.md`：Pages/CNAME、Releases 上传、离线签名、官方 vs 社区、撤回、DMCA、安全边界、上线清单。
- `marketplace/CONTRIBUTING.md`：ID、LICENSE/NOTICE、依赖、测试、权限最小化、非诊断、常见拒绝原因。

## 验证

- `node --check marketplace/site/app.js`：pass。
- `python -m py_compile .github/scripts/*.py`：pass；`python -m ruff check .github/scripts`：pass。
- Headless Edge CDP，1440×900 与 390×844，本地 `python -m http.server`：
  - `index.html`、`modules.html`、`developers.html`：JS 异常 0、console.error 0；favicon 404 已用 data URI 消除。
  - 官方 fixture：30 张卡、7 个分类；搜索 “garmin” 命中 2；详情弹窗 `open=true`，权限 1 条、含非诊断声明；社区 fixture：2 张卡、均显示“未审核”。
  - 移动端 `scrollWidth=390 / innerWidth=390`，三页无页面级横向溢出；移动弹窗宽 354，`scrollWidth` 仍 390。
  - 主题切换：system → dark，`aria-pressed=true`；亮/暗截图均已人工查看。
  - 空索引（无 index.json）：显示“索引尚未发布”，无卡片；缺失文件会产生 2 条 fetch 404 网络日志（预期，页面无 JS 错误）。
- `developers.html` 中 manifest 示例：提取后 JSON 解析通过；`schemas/module.schema.json` 校验 0 错误。
- 校验脚本负向：AGPL=1 error、owner 不一致=1、缺 license/非法 ID=3、checksums 不符=2，均 exit 1；正向 fixture 0 error 并生成 `.ehmod`。
- 索引脚本：`.github/scripts/pack_official_modules.py` 打包 30 个模块；fallback index 生成 30 条官方、0 条社区，2 个索引 `python -m json.tool` 通过。
- 两个 workflow YAML `yaml.safe_load` 解析通过。

## 未做 / 偏离

- 未部署、未建仓库、未买域名、未 commit；未改 backend/src、src、schemas、prompts、uploads。
- 未持久化亮/暗截图：文件所有权仅允许报告 `.md`，截图只放临时目录用于自查。
- 无头环境无法模拟用户手势，复制按钮显示“复制失败”；真实浏览器（localhost 安全上下文 + 用户点击）走 Clipboard API。
- 站点 GitHub 组织/仓库 URL 为占位；`marketplace/official|community/index.json` 待 H8 生成，当前本地模块页显示空状态。

## 跨区需求（需要别的 Agent 或指挥官处理）

- H8：产出 `scripts/build_marketplace_index.py`、`scripts/sign_marketplace_index.py`、`marketplace/official/index.json`、`marketplace/community/index.json`，并确认 `file` 字段与 CI 复制到 `_site/modules/` 的路径一致。
- 发布者：替换 `eclipse-health/eclipse-health` 占位 URL；创建首个 Release 上传 `.ehmod`；配置 `marketplace/CNAME` 与 DNS；用生产密钥离线重签索引后部署。
- H9 若能提供真实索引 URL/示例，可复用本页结构做应用内市场视觉对齐。

## 需要指挥官决策

- 许可证白名单：H10 要求 CI 拒绝 AGPL/无许可；CLAUDE.md 允许社区专有/付费。当前 PR 提交流程只接受 OSI 白名单；若专有社区模块也要走同一 PR，需决定是否在社区模式放行 `LicenseRef-Proprietary` 并强制显著标注。
- Pages 自动部署默认关闭（`MARKETPLACE_PUBLISH=true` 才开），是否在首个 Release 前开启。

## 建议下一批

- 真实仓库建好后跑一次 validate/publish 全链路，补 `actionlint` 与链接检查。
- 索引生成后做站点 E2E（下载 URL、签名展示、yanked/新版权限 diff）。
- 为开发者页加入可下载的 manifest 模板与 `.ehmod` 校验工具说明链接。

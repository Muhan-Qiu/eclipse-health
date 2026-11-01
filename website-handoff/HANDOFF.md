# Website Agent · 交接说明（eclipse-health.fit）

> 给负责官网/市场站的 Agent。先读本文件 + `PROMPT.md`，再读项目根 `CLAUDE.md`。
> 项目根：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 1. 站点现状

- 线上域名：**https://eclipse-health.fit/**（已验证 200）
- 托管：GitHub Pages，仓库 **`Muhan-Qiu/eclipse-health`**，分支 **`gh-pages`**（不是 main）
- 站点源码（事实源）：`marketplace/site/`
  - `index.html` 首页/下载
  - `modules.html` 模块市场（读 `official/index.json`、`community/index.json`）
  - `developers.html` 开发者文档
  - `styles.css` / `app.js`
- 市场索引源码：`marketplace/official/index.json`、`marketplace/community/index.json`（Ed25519 签名，当前 `keyId=dev-2026`）
- 模块包：`dist/modules/*.ehmod`（当前 32 个 = 官方 10 + 社区 22，含 `relay-sleep`、`relay-ecg`）
- 发布分支结构：
  ```
  gh-pages/
    CNAME                    # eclipse-health.fit
    index.html modules.html developers.html styles.css app.js
    official/index.json
    official/modules/*.ehmod
    community/index.json
    community/modules/       # 可为空
  ```
- 应用市场默认地址已是 `https://eclipse-health.fit/official/index.json`。

## 2. 发布流程（必须按此做）

1. 改 `marketplace/site/`（只改源码；不要直接改 gh-pages 分支文件）。
2. 如果模块/索引变了：
   - `backend\.venv\Scripts\python.exe scripts\pack_official_modules.py`
   - `backend\.venv\Scripts\python.exe scripts\build_marketplace_index.py`
3. 同步到 gh-pages（临时克隆、复制、提交、普通 push，**不要 force push**）：
   ```powershell
   $root = "C:\Users\qiumuhan\Documents\claude\心电智能体\v3"
   $tmp = "$env:TEMP\eh-gh-pages-update"
   if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
   $env:GIT_SSH_COMMAND = "ssh -o UserKnownHostsFile=C:/Users/qiumuhan/.claude/github_ssh_known_hosts -o StrictHostKeyChecking=yes"
   git clone -q --depth 1 --branch gh-pages ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git $tmp
   Copy-Item -Path "$root\marketplace\site\*" -Destination $tmp -Recurse -Force
   # 站点源码已按 data-depth 处理索引路径（根目录 ../official，en/ 用 ../../official），不要再改 app.js
   Copy-Item -Force "$root\marketplace\official\index.json" "$tmp\official\index.json"
   Copy-Item -Force "$root\marketplace\community\index.json" "$tmp\community\index.json"
   Copy-Item -Force "$root\dist\modules\*.ehmod" "$tmp\official\modules\"
   "eclipse-health.fit" | Set-Content "$tmp\CNAME"
   cd $tmp
   git add -A
   git -c user.name="Qiu Muhan" -c user.email="280846993+Muhan-Qiu@users.noreply.github.com" commit -m "Update marketplace site"
   git push origin gh-pages
   ```
4. 改完检查：
   - `https://eclipse-health.fit/`
   - `https://eclipse-health.fit/en/`、`/en/modules.html`、`/en/developers.html`
   - `https://eclipse-health.fit/official/index.json`（10 条）
   - `https://eclipse-health.fit/community/index.json`（22 条）
   - `https://eclipse-health.fit/module-copy.zh.json` 与 `module-copy.en.json`
   - 任取一个 `.ehmod` 链接 200。

## 3. 必须保留/不能破坏

- `CNAME` 必须是 `eclipse-health.fit`（不要改成 www 或删掉）。
- 市场索引签名：不要手工改 `marketplace/official/index.json` 的 `modules` 后直接发布；用 `scripts/build_marketplace_index.py` 重签。私钥在 `.secrets/`（gitignored），**不要提交/打印**。
- 站点 `app.js` 从 `official/index.json` / `community/index.json` 读数据；模块文件路径是相对索引的 `modules/<file>.ehmod`。
- 仓库链接使用 `https://github.com/Muhan-Qiu/eclipse-health`（已统一替换）。
- 站点为双语：根目录中文，`en/` 英文；模块详细文案在 `module-copy.zh.json` / `module-copy.en.json`，按模块 ID 覆盖索引里的名称与简介。
- 不要 push 到 main；只改 gh-pages。

## 4. 已知问题（用户明确要改）

1. **Logo 有问题（暂缓）**：用户 2026-11-01 明确说真正的 logo 还没定，先不要改。等品牌定稿后，再换 `src/branding/Logo.tsx` / `public/brand/favicon.svg` 对应的深绿涟漪版本。
2. **布局/排版**：首页、模块市场、开发者页已做一轮信息层级与移动端适配；后续用户会继续提具体改动。
3. **下载链接**：首页指向 `https://github.com/Muhan-Qiu/eclipse-health/releases`；`v0.1.0-alpha` 安装包已上传，页面标注「已发布」。发新版本时更新版本号与 Release 标签即可。
4. **模块市场页**：卡片已改为“功能优先”，详情页包含功能、输入输出、适用场景、限制与技术说明；自研模块已改名并配详细文案。
5. **开发者页**：已写清 PR 流程、许可证白名单、`io.github.<owner>.<name>`、NOTICE/署名与测试要求。
6. **生产签名**：当前索引是 dev key；上线前需用户用生产 Ed25519 私钥重签，并更新应用内置公钥。不要自己生成/替换生产钥。

## 5. 不要做

- 不要改应用核心代码、后端、模块实现；只改 `marketplace/site/**` 和必要时文档。
- 不要提交安装包/大权重到 git；不要 force push。
- 不要声称 Release/签名已完成，未验证就写未验证。

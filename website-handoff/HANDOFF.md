# Website Agent · 交接说明（eclipse-health.fit）

> 给负责官网/市场站的 Agent。先读本文件 + `PROMPT.md`，再读项目根 `CLAUDE.md`。
> 项目根：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 1. 站点现状

- 线上域名：**https://eclipse-health.fit/**（已验证 200）
- 托管：GitHub Pages，仓库 **`Muhan-Qiu/ecg-agent`**，分支 **`gh-pages`**（不是 main）
- 站点源码（事实源）：`marketplace/site/`
  - `index.html` 首页/下载
  - `modules.html` 模块市场（读 `official/index.json`、`community/index.json`）
  - `developers.html` 开发者文档
  - `styles.css` / `app.js`
- 市场索引源码：`marketplace/official/index.json`、`marketplace/community/index.json`（Ed25519 签名，当前 `keyId=dev-2026`）
- 模块包：`dist/modules/*.ehmod`（当前 32 个，含 `relay-sleep`、`relay-ecg`）
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
   git clone -q --depth 1 --branch gh-pages ssh://git@ssh.github.com:443/Muhan-Qiu/ecg-agent.git $tmp
   Copy-Item -Force "$root\marketplace\site\*" $tmp
   # 站点在根目录，索引路径要从 ../official 改成 official
   (Get-Content "$tmp\app.js") -replace '\.\./official/index\.json','official/index.json' -replace '\.\./community/index\.json','community/index.json' | Set-Content "$tmp\app.js"
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
   - `https://eclipse-health.fit/official/index.json`（32 条）
   - 任取一个 `.ehmod` 链接 200。

## 3. 必须保留/不能破坏

- `CNAME` 必须是 `eclipse-health.fit`（不要改成 www 或删掉）。
- 市场索引签名：不要手工改 `marketplace/official/index.json` 的 `modules` 后直接发布；用 `scripts/build_marketplace_index.py` 重签。私钥在 `.secrets/`（gitignored），**不要提交/打印**。
- 站点 `app.js` 从 `official/index.json` / `community/index.json` 读数据；模块文件路径是相对索引的 `modules/<file>.ehmod`。
- 仓库链接使用 `https://github.com/Muhan-Qiu/ecg-agent`（后续仓库改名后再统一替换）。
- 不要 push 到 main；只改 gh-pages。

## 4. 已知问题（用户明确要改）

1. **Logo 有问题**：站点用的 logo/图标与新版应用内深绿涟漪不一致；需要换成应用当前品牌：
   - `src/branding/Logo.tsx` / `src/components/common/eclipse-mark.tsx`（深绿同心环、由外向内收）
   - `public/brand/favicon.svg`、`public/brand/icon-1024.png`
   - `src-tauri/icons/*`（桌面图标）
   - 设计令牌：`src/index.css` 的 `--eh-signal` 等；不要用旧金色/黑底图标。
2. **布局/排版要重做**：首页、模块市场、开发者页需要更好的信息层级、间距、移动端适配；保持低饱和、与桌面应用一致的视觉，不要玻璃拟态/高饱和默认。
3. **下载链接**：首页指向 GitHub Releases/latest，但当前安装包还没有上传到 Releases；需要你在 GitHub Releases 上传 `eclipse health_0.1.0_x64-setup.exe` 后再确认链接，或改成实际 asset 链接。
4. **模块市场页**：32 个模块很多，需要分类/搜索/排序/分页或更好的网格；保留官方/社区切换与未审核标记。
5. **开发者页**：写清模块提交（GitHub PR + Actions）、许可证白名单（宽松 + GPL-3.0 兼容；AGPL/无许可拒绝）、`io.github.<owner>.<name>`、NOTICE/署名、测试要求。
6. **生产签名**：当前索引是 dev key；上线前需用户用生产 Ed25519 私钥重签，并更新应用内置公钥。不要自己生成/替换生产钥。

## 5. 不要做

- 不要改应用核心代码、后端、模块实现；只改 `marketplace/site/**` 和必要时文档。
- 不要提交安装包/大权重到 git；不要 force push。
- 不要声称 Release/签名已完成，未验证就写未验证。

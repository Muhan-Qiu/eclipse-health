# Website agent report · 2026-11-01

## 本轮完成

1. **英文版上线（独立页面）**
   - 新增 `marketplace/site/en/index.html`、`en/modules.html`、`en/developers.html`。
   - 每个页面页头都有中英切换；所有页面加了 `hreflang`（zh-CN / en / x-default）。
   - 模块市场 UI（搜索、筛选、详情、权限说明、错误提示、日期格式）全部按语言切换。
   - 索引路径改为按 `body[data-depth]` 计算：中文页 `../official`，英文页 `../../official`，本地与 gh-pages 都能用。

2. **模块讲解改为功能优先**
   - 新增 `module-copy.zh.json` / `module-copy.en.json`，按模块 ID 覆盖名称、一句话说明、功能清单、输入、输出、适用场景、限制与技术说明；32 个模块全部覆盖。
   - 卡片先展示「能做什么」，详情页展开完整功能、输入输出、限制、权限、依赖、扫描与 SHA-256。
   - 支持深链接：`modules.html?module=<id>` 自动打开详情（首页自研模块卡片已使用）。

3. **自研模块改名与详细文案**
   - `org.eclipsehealth.relay-ecg` → 显示名 **ECG 心搏分析**（ID 不变）。
   - `org.eclipsehealth.relay-sleep` → 显示名 **睡眠分期分析**（ID 不变）。
   - 同时更新两份 `module.json`、README 首段，重打包 `.ehmod` 并用 dev key 重签索引；`dist/modules` 与 gh-pages 已同步。
   - 首页新增「自研分析模块」区块：Cardia 2.0（内置）、ECG 心搏分析、睡眠分期分析，分别说明功能差异。

4. **首页与 GitHub**
   - 新增「一次导入，从波形看到报告」六项能力区块（导入、心搏分析、记录趋势、报告、AI 助手、本地开放接口）。
   - 所有 `github.com/eclipse-health/eclipse-health` 占位链接改为 `github.com/Muhan-Qiu/eclipse-health`。
   - 下载区改为 `v0.1.0 · 安装包待上传`，按钮指向真实 Releases 页，并如实说明上传后即生效。

5. **文档**
   - 更新 `website-handoff/HANDOFF.md`（发布流程、`-Recurse`、不再改写 app.js、en/ 与 module-copy 检查项、已知问题）。
   - 更新 `PROMPT.md` / `README.md`，标明 Logo 暂缓。

## 验证

- 本地静态服务器 + Playwright：
  - 中文、英文模块页均渲染 32 个模块，console 0 error。
  - 深链接打开详情正常；自研模块排在官方列表最前（ECG → 睡眠）。
  - 375/390px 下首页、模块页、开发者页均无横向溢出；详情弹窗宽度正常。
  - 中英切换、主题切换、搜索/分类筛选正常。
- 发布：已推送 `55b302f..1f53cfd` 到 `Muhan-Qiu/eclipse-health` 的 `gh-pages`。
- 线上验证（部署完成后）：
  - `/`、`/en/`、`/modules.html`、`/en/modules.html`、`/en/developers.html` 均 200；
  - `module-copy.zh.json` / `module-copy.en.json` 均 200；
  - `official/index.json` 32 条，自研模块名为「ECG 心搏分析」「睡眠分期分析」；
  - `official/modules/org.eclipsehealth.relay-ecg-0.1.0.ehmod` HEAD 200。

## 未做 / 需要用户

- **Logo 未改**：按要求等品牌定稿。
- **生产签名**：索引仍为 `dev-2026`；上线前需用生产 Ed25519 私钥重签并更新应用内置公钥。
- **安装包**：尚未上传 GitHub Releases；网站入口已指向 Releases，上传后自动可用。
- **厂商格式**：Apple/Samsung/华为手表格式仍标为实验性，文案已如实标注。

# 模块市场静态站与发布指南

> 2026-11-01 · 适用：GitHub Pages（或任意静态托管）
> 相关：`marketplace/site/`、`marketplace/CONTRIBUTING.md`、`docs/REGISTRY_AND_SCANNING_V1.md`、`.github/workflows/`

## 0. 范围

本指南覆盖静态站、索引发布、`Releases` 上传、签名、域名、下架与安全边界。**不做**上传后端、账号系统与支付；开发者身份使用 GitHub。

## 1. 站点结构

```text
marketplace/
├── site/                 # 纯静态站，无第三方框架
│   ├── index.html        # 下载 / 市场 / 开发者入口
│   ├── modules.html      # 读取 ../official/index.json 与 ../community/index.json
│   ├── developers.html   # 契约 v2、manifest、权限、PR 流程
│   ├── styles.css
│   └── app.js
├── official/index.json   # 官方签名索引（H8 构建脚本生成）
├── community/index.json  # 社区签名索引
├── modules/              # 可选：站内托管的 .ehmod
├── submissions/          # 开发者 PR 提交目录（约定）
├── CONTRIBUTING.md
└── CNAME                 # 可选：自定义域名
```

站点必须作为 `site/` 子目录部署，因为页面按 `../official/index.json` 读取同级索引；发布工作流会自动生成根目录跳转到 `site/` 的页面。

本地预览（面条路径必须通过 HTTP，不要直接双击 HTML）：

```powershell
cd <repo-root>
backend\.venv\Scripts\python.exe -m http.server 8123
# 打开 http://127.0.0.1:8123/marketplace/site/index.html
```

`modules.html` 在两个索引都不存在时会显示“索引尚未发布”，这是预期行为，不是控制台错误。

## 2. GitHub Pages 与域名

1. 新建 GitHub 仓库并把默认分支设为 `main`；启用 Actions。
2. 仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。
3. 首次发布前，设置仓库变量 `MARKETPLACE_PUBLISH=true`（Settings → Variables → Actions）。未设置时工作流只构建并上传产物，不部署。
4. 自定义域名：在 `marketplace/CNAME` 写一行域名（如 `market.example.org`），工作流会复制到站点根。DNS 添加：

| 记录 | 主机 | 值 |
| --- | --- | --- |
| CNAME | `market` | `<owner>.github.io` |
| A（apex，可选） | `@` | `185.199.108.153` / `.109.153` / `.110.153` / `.111.153` |

5. Pages 设置中勾选 **Enforce HTTPS**。证书由 GitHub 自动签发，通常几分钟到数小时。
6. 站点内 `https://github.com/eclipse-health/eclipse-health` 是占位地址；上线前全局替换为真实组织/仓库名（`marketplace/site/*.html`、文档与索引 `repository` 字段）。

## 3. 发布 `.ehmod` 到 Releases

1. 打包：`backend\.venv\Scripts\python.exe scripts\pack_official_modules.py`（官方）或作者自行打包。
2. 新建 Release，tag 使用模块版本（如 `v0.1.0`），上传 `<module-id>-<version>.ehmod`。
3. 在 Release 说明中公布 SHA-256：`Get-FileHash -Algorithm SHA256 <file>`。
4. 索引条目的 `sha256` 必须与实际文件一致；`file` 字段为 `modules/<name>.ehmod`，站点会优先使用索引中的下载 URL，其次按 `repository` + `/releases/download/v<version>/<file>` 构造 GitHub Releases 链接。
5. 不要把 `.ehmod` 提交进 Git 历史（大文件、无法审计）；用 Releases 或对象存储。

## 4. 索引构建与签名

- 官方构建脚本：`scripts/build_marketplace_index.py`（H8）。输出 `marketplace/official/index.json`、`marketplace/community/index.json`。
- CI（`.github/workflows/publish-marketplace.yml`）在 `main` 变更时调用该脚本；若脚本尚不存在，使用 `.github/scripts/build_marketplace_index.py` 兜底。`dist/modules/index.json` 缺失时，CI 先用 `.github/scripts/pack_official_modules.py` 重新打包（stdlib，无需后端依赖）。
- **CI 不接触生产私钥**。H8 脚本在缺少密钥时会生成一次性 dev 钥，仅用于开发；兜底脚本默认输出未签名索引。任何 CI 产物在交给正式应用前必须由维护者离线重签。
- 离线签名：

```powershell
# 私有钥放 .secrets/（必须 gitignored），不进入仓库、CI 或日志
backend\.venv\Scripts\python.exe scripts\sign_marketplace_index.py `
  --key .secrets\marketplace_ed25519.key `
  --index marketplace\official\index.json
```

- 应用内置公钥表按 `keyId` 匹配；轮换时保留旧公钥至少一个版本周期，并对新索引交叉签名。
- 签名覆盖除 `signature` 外的整个对象，canonical JSON 规则见 `docs/REGISTRY_AND_SCANNING_V1.md` §5 与 `prompts/130-marketplace-backend.md`。
- 签名失败时应用返回 `marketplace_signature_invalid` 并拒绝未验签数据；不要通过关闭校验来“修复”发布问题。

## 5. 官方索引 vs 社区索引

| 项 | 官方 | 社区 |
| --- | --- | --- |
| 维护者 | 项目维护者 | 社区/第三方 |
| 签名 | 官方 Ed25519 | 独立签名（可选，需公钥） |
| 模块来源 | 第一方 + 通过扫描的社区模块 | 任何 GitHub 身份模块 |
| 许可证 | 仅 OSI 开源 | 允许专有/付费，显著标注 |
| `verified` | `true`（仅代表索引来源） | `false`，显示“未审核” |
| 审核 | 自动扫描 | 自动扫描；无人工日常审核 |

“官方”不代表人工审核过每个模块；安装页仍展示扫描等级与权限。红色拒绝，黄色/橙色允许安装但显著标注。

## 6. 提交流程

1. 开发者按 `marketplace/CONTRIBUTING.md` 准备 `marketplace/submissions/<module-id>/`。
2. PR 触发 `.github/workflows/validate-module.yml`：schema、ID 命名空间、许可证白名单、LICENSE/NOTICE、路径安全、密钥扫描、打包与解包、checksums。
3. 失败阻止合并；通过后合并到 `main`。
4. `publish-marketplace` 构建索引并上传产物；维护者离线签名后再部署/发布。
5. 社区索引条目由维护者或社区在 `marketplace/community/*.json` 提供，构建脚本归一化后写入 `community/index.json`。

## 7. 撤回与下架

- 作者自行撤回：在索引中把版本标记 `yanked: true`，或发布新版本；应用提示“已被作者撤回，建议回滚”。
- 项目**不维护全局撤回列表**，也不做中心化版本封禁；已发布版本无法被官方阻断。
- 法律/安全底线除外：违法内容、恶意软件、侵犯版权或隐私的条目，维护者可下架索引条目并保留说明；这不等于日常人工审核。
- 用户可在本机屏蔽模块/作者，仅本机生效；举报仅作参考。

## 8. 版权与 DMCA

- 提交者声明拥有代码与资源的再分发权，并保留上游许可证与署名。
- 版权投诉请发送到仓库安全/治理邮箱（上线时填写），包含：作品描述、侵权 URL、联系方式、善意声明与准确性声明。
- 收到有效通知后，维护者会移除或禁用相关索引条目与站点资源，并通知提交者；可提交反通知。
- 重复侵权者将被拒绝后续提交。商标与人格权投诉按同一流程处理。

## 9. 安全边界

- 站点是纯静态页面：无登录、无上传、无遥测、无 cookie、无第三方脚本/CDN。索引数据按不可信文本渲染（`textContent`，不使用 `innerHTML`）。
- 隐私：不收集访问统计，不向任何服务上报已安装模块或健康数据；`modules.html` 只读取同源静态 JSON。
- 应用安装器才是信任边界：索引签名 → 条目哈希 → 包签名（若有）→ 安装；站点展示的风险等级不能替代本地校验。
- 所有模块输出必须标注“非医疗器械，不用于诊断或治疗”。站点在页脚与详情中重复该声明。
- 不在站点放置付费支付流程；付费/赞助只显示链接，核心不处理支付。

## 10. 上线检查清单

- [ ] 替换占位仓库/组织 URL，创建真实 Release 与 `.ehmod`
- [ ] `marketplace/CNAME` 与 DNS 记录一致，Pages 强制 HTTPS
- [ ] 生产公钥写入应用，`keyId` 与离线签名一致
- [ ] 用生产密钥重签索引，`python -m json.tool` 通过
- [ ] `modules.html` 在官方/社区/空索引三种状态下无 console error
- [ ] 移动端 390px 宽度无横向溢出
- [ ] 安全/治理邮箱可收信，DMCA 流程有人负责

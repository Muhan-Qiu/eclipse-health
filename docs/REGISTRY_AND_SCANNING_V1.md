# eclipse health · 注册表与自动扫描规范 v1（草案）

> 2026-10-28 · 状态：草案，待用户确认
> 前提：Q2 官方+社区+自定义源+本地安装；Q3 权限+签名+隔离+审计；Q8 纯自动扫描，不做人工审核。

## 0. 目标

- 任何人都能发布模块，不需要等官方人工审核。
- 用户安装前能看到：权限、风险等级、扫描结果、许可证、作者、版本。
- 恶意/损坏/挂羊头卖狗肉的模块能被快速阻断，但不依赖人工逐个人审。
- 注册表本身不托管大模型权重，只放索引、校验和与下载地址。

## 1. 源与信任级别

| 源 | 说明 | 信任标识 |
|---|---|---|
| 官方索引 | 项目维护，签名；第一方模块 + 通过扫描的社区模块 | `official` |
| 社区索引 | 社区维护，独立签名；同一 schema | `community` |
| 自定义源 | 用户填 URL；可签名也可不签名 | `custom` |
| 本地安装 | 用户选择 `.ehmod` 文件 | `local` |

- 应用默认内置官方索引地址，可添加多个源。
- 每个源有独立的公钥；签名校验失败时降级为 `unverified` 并显著警告。
- 官方索引的“官方”只代表索引来源，不代表每个模块都被人工审核；模块仍按扫描结果标注。

## 2. 索引格式 `index.json`

```json
{
  "schemaVersion": "1.0",
  "name": "eclipse health official",
  "generatedAt": "2026-10-28T00:00:00Z",
  "channel": "stable",
  "signature": { "keyId": "official-2026", "sig": "base64..." },
  "modules": [
    {
      "id": "org.eclipsehealth.samsung",
      "type": "device-adapter",
      "name": "Samsung Health ECG",
      "summary": "Import Samsung Health ECG exports",
      "license": "GPL-3.0-only",
      "author": { "name": "eclipse health", "verified": true },
      "homepage": "https://...",
      "repository": "https://...",
      "tags": ["samsung", "wearable", "csv"],
      "pricing": { "model": "free", "url": null },
      "latest": "1.0.0",
      "versions": [
        {
          "version": "1.0.0",
          "apiVersion": "1.0",
          "engines": { "eclipse": ">=1.0 <2.0" },
          "publishedAt": "2026-10-28T00:00:00Z",
          "download": {
            "url": "https://github.com/.../samsung-1.0.0.ehmod",
            "sha256": "...",
            "size": 48213,
            "mirrors": []
          },
          "permissions": ["files:user-selected", "records:write"],
          "scan": {
            "status": "passed",
            "risk": "green",
            "scannedAt": "2026-10-28T00:00:00Z",
            "reportUrl": "https://.../scan/....json"
          },
          "signature": { "keyId": "author-key-1", "sig": "base64..." },
          "changelog": "Initial release",
          "yanked": false
        }
      ]
    }
  ]
}
```

## 3. 模块条目规则

- `id`：官方前缀 `org.eclipsehealth.*` 保留；社区模块使用 `io.github.<GitHub 用户名或组织>.<模块名>`，由扫描器校验仓库归属与 ID 一致；无 GitHub 身份的模块只能走自定义源并标记 `unverified`。
- `latest`：稳定通道最新版本；beta 通过 `channel` 或 `versions[].channel` 区分。
- `versions`：按时间倒序；保留历史版本以便回滚与固定版本。
- `yanked`：标记后应用不再推荐安装，但已安装用户收到安全提示。
- `download.url`：HTTPS；GitHub Releases、对象存储、自建 CDN 均可。
- `download.sha256`：必填；应用安装前强制校验。
- `permissions`：该版本实际权限；与上一版本 diff，新增权限触发重新授权。
- `scan`：扫描状态、风险等级、报告地址；应用安装页必须展示。
- `pricing`：`free` / `paid` / `sponsor`；核心不处理支付，只展示链接。
- 大模型权重：可在 `.ehmod` 内，也可用 `modelFiles[]` 单独 URL；都需 sha256。

## 4. 版本、通道与撤回

- 模块版本 SemVer；索引 schema 版本独立。
- 通道：`stable`、`beta`；用户可按模块选择。
- `yanked`：**作者自行标记撤回**；应用提示“已被作者撤回，建议回滚”。
- 项目**不维护全局撤回列表**（Q25）；已发布版本无法被中心化阻断。
- 版本固定：用户可锁死某模块版本；不自动更新。

## 5. 签名与密钥

- 官方索引：项目维护的 Ed25519 密钥，公钥内置应用；私钥离线/CI 受控。
- 作者签名：可选；`ehmod sign` 生成 `signature.json`；公钥可发布在作者主页/索引。
- 应用校验顺序：索引签名 → 条目哈希 → 包签名（若有）→ 安装。
- 密钥轮换：`keyId` + 交叉签名；旧公钥保留至少一个版本周期。
- 撤回：作者可撤回自己的版本；项目不提供全局密钥撤销或版本封禁。

## 6. 自动扫描流水线

发布时（索引服务端）与安装时（客户端轻量复核）执行：

| 阶段 | 检查 | 失败处理 |
|---|---|---|
| S0 结构 | manifest schema、ZIP 路径穿越、zip bomb、符号链接、文件数/大小上限 | 拒绝 |
| S1 完整性 | sha256、签名、索引签名 | 拒绝/降级 |
| S2 元数据 | id 命名空间、许可证、版本、兼容范围、模型卡 | 拒绝/警告 |
| S3 依赖 | OSV / pip-audit；已知高危依赖 | 高危拒绝，中危警告 |
| S4 静态代码 | bandit / semgrep 规则：`subprocess`、`eval`、`exec`、反序列化、混淆、可疑网络 | 高危拒绝 |
| S5 密钥扫描 | 仓库/包内不得含 API Key、私钥、令牌 | 拒绝 |
| S6 权限 diff | 与上一版本比较；新增 `records:delete`、`network`、`system:background`、`ui:custom` 重点标记 | 警告/升风险 |
| S7 网络白名单 | `network` 权限必须列 `allowedHosts`；禁止通配 `*` | 拒绝 |
| S8 模型校验 | 仅 ONNX/safetensors；魔数、哈希、大小；拒绝 pickle；远程模型需声明 | 拒绝 |
| S9 动态沙箱（可选） | 在受限容器/进程中启动模块，喂假数据，监控文件/网络/子进程 | 警告/升风险 |
| S10 打分 | 汇总为 green/yellow/orange/red | 红拒绝；橙黄标注 |

客户端安装时至少做：S0、S1、S6、S8 的本地复核；服务端扫描报告只作参考，不能替代本地校验。

## 7. 风险分级

| 等级 | 典型规则 | 用户看到 |
|---|---|---|
| `green` | 无网络、只读用户选择文件、无删除、签名有效、扫描干净 | 低风险 |
| `yellow` | 有 `network`（白名单）、`records:read`、未签名但哈希正确、专有许可 | 中风险 |
| `orange` | `records:delete`、`system:background`、`ui:custom`+网络、动态扫描有警告、新作者 | 高风险 |
| `red` | 发现密钥、恶意模式、签名无效、路径穿越、pickle 模型、命中撤回列表 | 拒绝安装 |

- 风险等级是**提示**，不是安全保证；安装页必须用直白语言解释权限。
- “官方模块”也走同一套扫描；第一方签名只代表来源可信。

## 8. 安装页必须展示

- 模块名、作者（是否认证）、来源（official/community/custom/local）。
- 版本、大小、更新时间、许可证、主页/仓库。
- 权限逐项中文解释（如“读取你导入的心电文件”“访问网络：api.example.com”）。
- 风险等级与扫描摘要；可展开完整报告。
- 是否签名；未签名时需手动勾选“我了解风险”。
- 付费/赞助标识；核心不处理支付。
- 升级时：新增权限高亮，必须重新确认。

## 9. 发布流程

1. 开发者 `ehmod build` 生成 `.ehmod` 与 checksums。
2. 可选 `ehmod sign`。
3. 上传包到 GitHub Releases / 自建 CDN。
4. 向索引提交条目（官方索引可 PR 或自动化 API；社区索引由维护者决定）。
5. 扫描流水线执行；`green/yellow/orange` 自动入库，`red` 拒绝并给出原因。
6. 发布后持续监控：撤回列表、依赖漏洞、用户举报。

> 说明：Q8 决定“不做人工审核”，因此上述第 5 步是自动合入；项目维护者仍保留对违法/恶意内容的下架权（法律与安全底线），这不是日常审核。

## 10. 更新检查与隐私

- 默认启动时检查一次，之后每 24h；可关闭/改频率。
- 默认拉取**完整索引快照**并本地缓存，避免逐模块请求泄露“用户装了什么”。
- 不向注册表上报已安装模块列表、使用频率、记录内容。
- 下载计数仅由 CDN 聚合日志统计，不在客户端埋点；是否展示由用户决定。

## 11. 滥用与举报

- 项目**不做社区索引治理**（Q26），上架完全依赖自动扫描（Q8）。
- **作者自行撤回**版本；项目不维护全局撤回列表（Q25）。
- 应用提供**用户本地屏蔽列表**：用户可屏蔽某个模块/作者，仅本机生效。
- 用户举报仅作参考，不触发全局下架；法律强制要求的下架除外。
- 医疗宣称：模块描述不得声称诊断/治疗；扫描规则检测“诊断”“治愈”等词并标记高风险。

## 12. 离线与内网

- 支持本地 `index.json` + `.ehmod` 文件安装。
- 企业/医院可自建镜像：完整复制索引与包，签名可选。
- 离线模式下不检查更新，安装页标注“离线源”。

## 13. 决策记录

已定（2026-10-28）：

- Q21 索引托管：**GitHub Pages 静态签名 JSON**，可镜像。
- Q22 扫描深度：**静态扫描**；动态沙箱与第三方病毒扫描暂不做。
- Q23 下载统计：**完全不做**，客户端无埋点、不向注册表上报安装列表。
- Q24 命名空间：**GitHub 身份绑定**，社区 ID 为 `io.github.<owner>.<name>`，扫描器校验仓库归属；官方前缀保留。
- Q25 撤回机制：**作者自行撤回**；项目不维护全局撤回列表。
- Q26 社区治理：**不治理**；上架依赖自动扫描，用户举报仅作参考。
- Q27 非 GitHub 开发者：**必须 GitHub** 才能进入索引；不接受其他身份上架。
- Q28 警告处理：**红色拒绝；黄色/橙色允许安装但显著标注**风险与权限。

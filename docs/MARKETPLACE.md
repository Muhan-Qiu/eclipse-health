# 模块市场 · 应用内行为与安全边界

> 2026-11-01 · H8。索引格式、签名与发布流程见 `marketplace/README.md`；
> 注册表与扫描规范见 `docs/REGISTRY_AND_SCANNING_V1.md`。

## 1. 范围

应用内市场只做四件事：

1. 从官方/社区静态索引读取模块列表；
2. 校验索引签名与条目格式；
3. 下载 `.ehmod`，校验 `size` / `sha256`；
4. 交给现有 `ModuleManager.install(archive, enable=False)` 安装。

不做自动更新、评分、审核、支付，也不修改模块内核。

## 2. 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `EH_MARKETPLACE_OFFICIAL_URL` | 仓库内 `marketplace/official/index.json` 的 `file://` | 官方索引 URL；设为空字符串表示关闭 |
| `EH_MARKETPLACE_COMMUNITY_URL` | 仓库内 `marketplace/community/index.json` 的 `file://` | 社区索引 URL；设为空字符串表示关闭 |
| `EH_MARKETPLACE_PUBLIC_KEY` | 包内 `marketplace/public_key.txt` | 覆盖内置公钥表（测试/镜像用） |

未配置（或本地默认索引尚未构建）时，接口返回 `503 marketplace_not_configured`，服务照常启动。

## 3. REST

挂载点 `/api/v1/marketplace`：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/index?source=official\|community&q=&category=` | 过滤后的模块列表；`q` 匹配 id/名称/描述/作者/分类 |
| GET | `/updates` | 已安装模块与两个索引的最高版本比较；官方索引优先 |
| POST | `/install` | `{source, moduleId, version?}`；`version` 省略时取最高版本 |
| GET | `/sources` | 两个源的 URL、是否配置、内置 keyId 列表 |

错误体与核心 API 一致：`{code, message, details}`。

## 4. 安装流程与错误码

```text
source → 读索引（≤5MB，15s 超时，缓存 10 分钟）
       → 验签（Ed25519，keyId 查内置公钥表）
       → 找条目（id + version，semver）
       → 检查 minCoreVersion
       → 下载（≤100MB；https / localhost / file；拒绝私网重定向）
       → 校验 size + sha256
       → 写临时 .ehmod
       → manager.install(..., enable=False)
       → audit marketplace.install
       → 删除临时文件
```

| 错误码 | HTTP | 场景 |
|---|---|---|
| `marketplace_not_configured` | 503 | 源未配置或本地索引未构建 |
| `marketplace_source_invalid` | 422 | source 不是 official/community |
| `marketplace_fetch_failed` | 502 | 索引网络错误、非 2xx、重定向异常 |
| `marketplace_index_invalid` | 502 | schema/字段/semver/sha256/路径/重复条目不合法 |
| `marketplace_signature_invalid` | 502 | 缺签名、keyId 无公钥、base64 或 Ed25519 校验失败 |
| `marketplace_module_not_found` | 404 | 索引没有该模块或版本 |
| `marketplace_download_failed` | 502 | 包不存在、连接失败、非 2xx |
| `marketplace_download_url_rejected` | 400 | 非 https/localhost/file，或重定向到私网/本地文件 |
| `marketplace_checksum_mismatch` | 422 | size 或 sha256 与索引不一致 |
| `marketplace_resource_exceeded` | 413 | 索引 >5MB 或包 >100MB |
| `marketplace_incompatible_core` | 409 | `minCoreVersion` 高于当前核心 |

验签失败时不返回任何条目；缓存只保存已验签的索引。

## 5. 安全边界

- **索引不可信直到验签**：签名覆盖除 `signature` 外的整个对象，canonical JSON 规则固定。
- **社区不因签名而可信**：`source=community` 的条目 `verified` 恒为 `false`；索引签名只证明索引未被篡改。
- **下载地址白名单**：https 任意；http 仅 localhost/127.0.0.1；file 仅本地索引解析；重定向逐跳校验，私网/本地文件重定向拒绝。
- **完整性**：先按 `Content-Length` 快速拒绝超大包，流式写入时再次累计上限；安装前重新计算 sha256。
- **临时文件**：每次安装使用独立临时目录，成功、校验失败、manager 异常都会清理。
- **审计**：`marketplace.install` 记录 source / keyId / id / version / sha256 / ok / errorCode，不记录包内容或健康数据。
- **隐私**：不向索引上报已安装列表；索引整体拉取后本地缓存，避免逐模块探测。

## 6. 未做 / 后续

- 应用内 UI（H9）与静态站/上传表单（H10）。
- 自动更新、下载统计、评分与人工审核。
- 作者签名（包内 `signature.json`）与扫描报告字段目前不在索引契约内。

# eclipse health · 模块市场索引

> 面向维护者与发布者。应用内行为与安全边界见 `docs/MARKETPLACE.md`；索引字段以 `prompts/130-marketplace-backend.md` 与本文为准。

## 1. 官方源与社区源

| 源 | 文件 | 信任标识 | 说明 |
|---|---|---|---|
| 官方 | `official/index.json` | `official` + `verified=true` | 项目维护、项目签名；条目来自 `modules/official/**` |
| 社区 | `community/index.json` | `community` + `verified=false` | 社区维护、独立签名；条目来自 `community/*.json` 或社区提交 |

两个索引结构相同，应用分别配置 URL（`EH_MARKETPLACE_OFFICIAL_URL` / `EH_MARKETPLACE_COMMUNITY_URL`）。社区条目的 `verified` 即使写成 `true`，后端也会强制降为 `false`。

## 2. 索引格式

```json
{
  "schemaVersion": "1",
  "source": "official",
  "generatedAt": "2026-11-01T00:00:00Z",
  "keyId": "dev-2026",
  "modules": [
    {
      "id": "io.github.owner.name",
      "name": "…",
      "version": "0.1.0",
      "type": "analysis-model",
      "description": "…",
      "author": "…",
      "license": "MIT",
      "repository": "https://github.com/…",
      "permissions": ["records:read"],
      "dependencies": ["pkg>=1,<2"],
      "minCoreVersion": "0.1.0",
      "categories": ["analysis"],
      "verified": true,
      "file": "modules/io.github.owner.name-0.1.0.ehmod",
      "size": 12345,
      "sha256": "<64 位小写十六进制>"
    }
  ],
  "signature": "base64(Ed25519(canonical_json_without_signature))"
}
```

- `version`、`minCoreVersion` 必须是 SemVer（`x.y.z`，可带预发布号）。
- `sha256` 必须是 64 位小写十六进制；`size` 必须大于 0 且不超过 100MB。
- `file` 为相对路径（`modules/*.ehmod`）或 `https:` / `http://localhost` / `file:` 绝对地址；拒绝 `..`、反斜杠与其它协议。
- 同一 `(id, version)` 只能出现一次。
- `categories` 用于客户端筛选；官方构建按模块类型映射（`analysis-model -> analysis` 等）。

## 3. 签名与公钥

签名对象是**除 `signature` 外的整个 JSON 对象**，用 canonical JSON：

```python
json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

- 私钥：`.secrets/marketplace_ed25519.key`（PEM / 64 位 hex / 32 字节原始值均可），已在 `.gitignore` 中排除。
- 公钥表：`backend/src/eclipse_health_backend/marketplace/public_key.txt`，格式为 `keyId=<id>` 后跟 PEM 块；可有多个 keyId。应用按索引的 `keyId` 查表验签。
- 缺少私钥时，`build_marketplace_index.py` 会生成一次性开发密钥并写公钥；**生产发布必须替换为维护者离线密钥**。

生产签名（私钥不进入 CI）：

```powershell
backend\.venv\Scripts\python.exe scripts\sign_marketplace_index.py `
  --key .secrets\marketplace_ed25519.key `
  --key-id official-2026 `
  --index marketplace\official\index.json `
  --public-key-out backend\src\eclipse_health_backend\marketplace\public_key.txt
```

密钥轮换：新索引使用新 `keyId`，公钥表保留旧 `keyId` 至少一个版本周期；旧索引仍可验签。

## 4. 构建流程

1. 先打包模块：`backend\.venv\Scripts\python.exe scripts\pack_official_modules.py`（生成 `dist/modules/*.ehmod` 与 `dist/modules/index.json`）。
2. 构建并签名索引：

```powershell
backend\.venv\Scripts\python.exe scripts\build_marketplace_index.py
```

脚本读取：

- `dist/modules/index.json` 与 `modules/official/*/module.json` → 官方条目；
- `marketplace/community/*.json`（可选；单条对象、数组或 `{"modules": [...]}`）→ 社区条目；
- 包内实际 `size` / `sha256` 以文件重新计算，不信任手填值。

输出：

- `marketplace/official/index.json`
- `marketplace/community/index.json`
- `backend/src/eclipse_health_backend/marketplace/public_key.txt`

内置模块 `org.eclipsehealth.cardia` 随安装包分发，不进市场索引。任一官方模块缺少 `.ehmod` 时构建失败并提示先运行打包脚本。

## 5. 发布 `.ehmod`

1. 把 `dist/modules/<id>-<version>.ehmod` 上传到 GitHub Releases 或对象存储（不要提交进 Git 历史）。
2. 索引的 `file` 为 `modules/<文件名>`；应用按索引 URL 解析相对路径，找不到时回退到同级 `../modules/` 与仓库 `dist/modules/`（本地开发）。
3. `.ehmod` 的 `sha256` 必须与索引一致；应用下载后会再次计算并比对。
4. 索引不托管大模型权重；权重随包或单独 URL 分发，均需 sha256。

## 6. 安全边界（摘要）

- 应用只接受 https、http://localhost 或 file 的包地址；重定向到私网/本地文件会被拒绝。
- 下载上限 100MB；索引上限 5MB、超时 15 秒。
- sha256 或 size 不匹配 → 不安装；验签失败 → `marketplace_signature_invalid`（502），绝不返回未验签数据。
- 安装复用现有模块内核（路径穿越、zip bomb、manifest 校验、依赖安装）。
- 仅静态索引，不做下载统计、不上报安装列表。

# H8 · 模块市场后端（签名索引 + 下载安装 + 更新检查）

> 先读 `prompts/00-COMMON.md`、`docs/REGISTRY_AND_SCANNING_V1.md`、`docs/MODULE_CONTRACT_V2.md`、`modules/manager.py`、`scripts/pack_official_modules.py`。
> **思考强度：low。** 只做“读索引、验签、下载、交给现有 manager 安装”，不重写模块系统。

## 目标

应用内市场：从官方/社区静态索引浏览模块，下载 `.ehmod`，校验签名与 sha256，复用现有 `manager.install()` 安装；支持版本更新检查。官方与社区分开。

## 索引格式（事实源）

```json
{
  "schemaVersion": "1",
  "source": "official",
  "generatedAt": "2026-11-01T00:00:00Z",
  "keyId": "dev-2026",
  "modules": [
    {
      "id": "io.github.owner.name",
      "name": "…", "version": "0.1.0", "type": "analysis-model",
      "description": "…", "author": "…", "license": "MIT",
      "repository": "https://github.com/…",
      "permissions": ["records:read"],
      "dependencies": ["pkg>=1,<2"],
      "minCoreVersion": "0.1.0",
      "categories": ["cardiac"],
      "verified": true,
      "file": "modules/io.github.owner.name-0.1.0.ehmod",
      "size": 12345,
      "sha256": "…"
    }
  ],
  "signature": "base64(Ed25519(canonical_json_without_signature))"
}
```

- canonical JSON：`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` UTF-8。
- 签名覆盖除 `signature` 外的整个对象；`keyId` 对应应用内置公钥表。
- 官方/社区两个索引；社区条目 `verified=false`。

## 交付

### 1. 签名与构建脚本

- `scripts/build_marketplace_index.py`：
  - 读取 `dist/modules/index.json` 与各 `modules/official/*/module.json`，生成官方索引条目（含 categories、verified=true、file/size/sha256）；
  - 读取 `marketplace/community/*.json`（可选）生成社区索引；
  - 用 `.secrets/marketplace_ed25519.key` 签名（不存在则生成 dev 钥；私钥必须 gitignored）；
  - 输出 `marketplace/official/index.json`、`marketplace/community/index.json`；
  - 公钥写 `backend/src/eclipse_health_backend/marketplace/public_key.txt`（PEM 或 hex + keyId），提交。
- `scripts/sign_marketplace_index.py`：对已有索引重签（生产钥由用户离线提供）。
- `.gitignore` 加 `.secrets/`；README 说明生产密钥替换与轮换（keyId）。

### 2. 后端

- 新建 `backend/src/eclipse_health_backend/marketplace/`：
  - `models.py`：Pydantic 索引/条目/安装结果。
  - `index.py`：从配置的 URL 或本地 `file://` 读取索引，httpx 超时 15s、最大 5MB；验签；缓存 10 分钟；校验条目不重复、版本 semver、sha256 格式；签名失败 → 502 `marketplace_signature_invalid`，不返回未验签数据。
  - `service.py`：
    - `install(source, moduleId, version)`：找条目 → 下载（http/https/file；仅 https 或 localhost/file，拒绝私网重定向）→ 限制 100MB → 校验 size/sha256 → 写临时 `.ehmod` → `manager.install(archive, enable=False)` → 返回模块摘要；失败清理临时文件；
    - `updates()`：对比已安装模块版本与索引，返回可更新项；
    - 审计 `marketplace.install`（keyId? source/id/version/sha256/ok）。
  - `api.py`：`GET /api/v1/marketplace/index?source=official|community&q=&category=`、`GET /api/v1/marketplace/updates`、`POST /api/v1/marketplace/install` `{source,moduleId,version}`、`GET /api/v1/marketplace/sources`（配置、keyId、官方/社区 URL）。
  - 配置：`EH_MARKETPLACE_OFFICIAL_URL`、`EH_MARKETPLACE_COMMUNITY_URL`；默认指向 `marketplace/official/index.json` 的 `file://`（开发）或空（未配置时 API 返回 `marketplace_not_configured`，不崩溃）。
- 测试：签名通过/篡改失败、条目校验、下载 sha256 失败、路径/重定向拒绝、安装调用 manager（mock）、updates、未配置、社区 verified=false。

### 3. 文档

- `marketplace/README.md`：索引格式、签名流程、官方/社区区别、发布步骤；`docs/MARKETPLACE.md` 简述应用内行为与安全边界。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/marketplace/**`（新建）
- `backend/src/eclipse_health_backend/api/__init__.py`（挂 marketplace router）
- `backend/tests/marketplace/**`（新建）
- `scripts/build_marketplace_index.py`、`scripts/sign_marketplace_index.py`（新建）
- `marketplace/official/index.json`、`marketplace/community/index.json`、`marketplace/README.md`
- `docs/MARKETPLACE.md`（新建）
- `.gitignore`
- `reports/H8-marketplace-report.md`

## 明确不做

- 不做网站/上传表单（H10）、不做应用内 UI（H9）。
- 不做自动更新；不做评分/审核系统；不复制模块代码。
- 不新增依赖（httpx/cryptography 已装）；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\marketplace -q
backend\.venv\Scripts\python.exe scripts\build_marketplace_index.py
```

报告 `reports/H8-marketplace-report.md`，≤80 行。

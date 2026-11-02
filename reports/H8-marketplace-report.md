# 报告 · H8 模块市场后端（签名索引 + 下载安装 + 更新检查）
状态：完成

## 交付
- `backend/src/eclipse_health_backend/marketplace/`：`models.py`（索引/条目）、`index.py`（读取、Ed25519 验签、条目校验、10 分钟缓存）、`service.py`（下载、size/sha256 校验、`manager.install(enable=False)`、updates、审计）、`api.py`（4 个 REST 接口）、`config.py`、`errors.py`、`public_key.txt`（dev-2026）。
- `backend/src/eclipse_health_backend/api/__init__.py`：懒挂载 `/api/v1/marketplace`，导入失败不影响核心启动。
- `scripts/build_marketplace_index.py`：读 `dist/modules/index.json` + `modules/official/*/module.json` + 可选 `marketplace/community/*.json`，重新计算 size/sha256，生成并签名两个索引；缺失 `.secrets/marketplace_ed25519.key` 时生成 dev 钥。
- `scripts/sign_marketplace_index.py`：离线重签已有索引，可选回写公钥表。
- `marketplace/official/index.json`（30 个模块，cardia 内置不收录）、`marketplace/community/index.json`（空，已签名）、`marketplace/README.md`。
- `docs/MARKETPLACE.md`：应用内行为、配置、错误码与安全边界。
- `.gitignore`：新增 `.secrets/`；私钥已验证被忽略。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend` → All checks passed（exit 0）。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\marketplace -o addopts="" -q` → 36 passed in 1.24s。
  覆盖：验签通过/篡改/缺签名/keyId 未知、社区 verified=false、重复条目、semver/sha256/路径非法、未配置、缓存、file 下载安装、sha256/size 失败、路径穿越、版本选择、HTTP localhost、非回环 http 拒绝、私网重定向拒绝、超 100MB 拒绝、updates（官方优先/未安装过滤/社区）、REST 错误体、审计成功与失败。
- `backend\.venv\Scripts\python.exe scripts\build_marketplace_index.py` → 30 official / 0 community，0.46s，exit 0；二次运行复用 dev 钥。
- 回归：`pytest backend/tests/api -q` → 42 passed in 4.06s。
- 端到端冒烟（完整 app）：`/api/v1/marketplace/sources|index|updates` 均 200；索引验签通过。
- `sign_marketplace_index.py --index marketplace/community/index.json` → 重签成功，后端仍可验签。

## 未做 / 偏离
- 只做索引签名校验；`.ehmod` 包内作者签名（契约中的可选 `signature.json`）未实现，提示词未要求。
- 社区索引目前与官方共用 dev 钥；生产需用独立密钥/`keyId` 离线重签（README 已写明流程）。
- `file` 相对索引 URL 解析；本地开发额外回退 `../modules/` 与 `dist/modules/`（包内容仍强制 sha256，不影响安全）。
- 索引 `minCoreVersion` 按严格 `x.y.z` 校验；构建脚本已把 `>=1.0 <2.0` 归一化到 `1.0.0`。
- 未做网站/上传表单（H10）与应用内 UI（H9），未改模块内核、未提交。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `.github/scripts/build_marketplace_index.py`（H10 兜底）把 `>=1.0 <2.0` 输出为 `minCoreVersion: "1.0"`，H8 后端会以 `marketplace_index_invalid` 拒绝；建议 H10 改为归一化 `x.y.z` 或直接删除兜底脚本。
- H9 UI 可直接消费：`GET /api/v1/marketplace/index`（含 `keyId`/`count`）、`/sources`、`/updates`、`POST /install`；错误体 `{code,message,details}`。
- H10 站点读取的 `file` 为站点相对路径（`modules/…`），与 H8 的索引目录相对解析存在一层目录差异；发布时应把 `.ehmod` 放到索引同级 `modules/` 或改为绝对 HTTPS URL。
- 当前仓库内 `marketplace/official/index.json` 为 dev 钥签名；正式发布前需维护者在离线环境用生产钥重签并更新 `public_key.txt`。

## 需要指挥官决策
- 是否允许 dev 签名索引随仓库提交（当前按提示词要求提交，便于本地直接可用）。
- 生产密钥的保管与 `keyId` 命名（当前默认 `dev-2026`）。
- 社区索引是否使用与官方不同的密钥；如需，需要扩展构建脚本参数。

## 建议下一批
- H9：市场列表/详情/安装确认 UI，展示 verified、权限、size、sha256 与错误码。
- 包级签名校验（`ehmod sign`）与扫描报告字段接入索引。
- 更新频率/通道（stable/beta）与用户关闭检查更新的设置项。

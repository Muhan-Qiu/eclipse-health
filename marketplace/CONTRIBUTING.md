# 向 eclipse health 提交模块

本文件是第三方模块的提交清单。契约事实源是 `schemas/module.schema.json` 与 `docs/MODULE_CONTRACT_V2.md`；本文件只解释流程与红线。

## 1. 提交前必须满足

### 身份与命名

- 模块 ID 使用 `io.github.<GitHub 用户名或组织>.<模块名>`，全小写，点分段，例如 `io.github.octocat.heart-rate`。
- ID 中的 owner 必须与 PR 作者或仓库所有者一致；扫描器按 GitHub 身份校验。
- `org.eclipsehealth.*` 前缀保留给项目维护者，社区提交不得使用。
- 版本使用 SemVer（`1.2.3`、`1.2.3-beta.1`）；发布后版本号不可复用。

### 许可证与署名

- 必须有 `LICENSE` 文件（完整许可证文本），`module.json` 的 `license` 使用 SPDX 标识。
- 允许：MIT、MIT-0、ISC、BSD-2-Clause、BSD-3-Clause、Apache-2.0、MPL-2.0、GPL-2.0/3.0（含 `-or-later`）、LGPL-2.1/3.0、Unlicense、CC0-1.0、Zlib、BSL-1.0。
- 拒绝：AGPL、SSPL、BUSL、`LicenseRef-*`、`NOASSERTION`、无许可证或无法确认再分发权的内容。
- Apache-2.0 必须同时提供 `NOTICE`；不得删除上游版权头。修改上游代码时在 README 说明修改点与日期。
- 保留上游 LICENSE/NOTICE 到模块目录；在 README 与 description 中写清 upstream 仓库、原版权人与你的角色。不得暗示上游或 eclipse health 为你背书。

### 权限最小化

- 只声明实际用到的权限；`network` 必须同时给出具体 `allowedHosts`，禁止 `*`。
- `records:delete`、`system:background`、`ui:custom` 会被标为高风险，需在 PR 中说明理由。
- 升级新增权限必须能让用户重新确认，不得静默提权。
- 权限说明写中文（安装页展示），例如“读取用户导入的心电文件”。

### 依赖

- `dependencies` 只接受 PEP 508（包名、extra、版本范围、环境标记）；拒绝 URL、`git+`、本地路径、`file:`、`-e`。
- 每个模块使用独立 venv；锁版本或给出上界，避免上游大版本破坏。
- 模型权重仅允许 ONNX / safetensors；远程权重必须给 sha256。禁止 pickle。
- 不得把 API Key、私钥、令牌、`.env` 或用户健康数据打进包；token 存 OS 密钥库。

### 测试

- `python -m json.tool module.json` 通过，且通过 `schemas/module.schema.json`。
- 主路径在干净临时目录运行通过；空输入、非法参数、未知方法返回结构化 JSON-RPC 错误。
- 断网、超时、空数据有明确错误码；大结果写临时文件。
- 打包后的 `.ehmod` 能在干净目录解包并启动一次，`checksums.json` 与文件一致。
- UI 模块附亮色/暗色截图；日志中不得出现波形、备注或原始文件名。

### 非诊断

- 所有分析/评分输出必须带“非医疗器械，不用于诊断或治疗”，保留 signal quality 与置信度字段（如适用）。
- 名称、描述、README 不得声称诊断、治愈或替代医生。扫描器会检测相关词并升风险。

## 2. 目录布局

```
marketplace/submissions/<module-id>/
├── module.json
├── src/
│   └── main.py           # 与 entry.python 一致
├── LICENSE
├── NOTICE                # Apache-2.0 必需
├── README.md             # 用法、权限、数据来源、非诊断声明
└── tests/                # 建议
```

模块 ID 与文件夹名必须一致。不要把 `venv/`、`__pycache__/`、`.git/`、`.env`、`*.pem`、`*.key` 提交进 PR。

## 3. 本地自检

```bash
python -m json.tool marketplace/submissions/<module-id>/module.json
python -m pip install jsonschema
python .github/scripts/validate_module.py marketplace/submissions/<module-id>
```

校验脚本会重新打包到 `dist-ci/`，并检查 schema、ID 命名空间、许可证白名单、LICENSE/NOTICE、路径安全、密钥模式、`.ehmod` 可解包与 checksums。

## 4. PR 流程

1. Fork 仓库，创建分支，把模块放到 `marketplace/submissions/<module-id>/`。
2. 使用 `.github/PULL_REQUEST_TEMPLATE/module.md` 填写 PR：作者、许可证、上游、权限、测试、截图、非诊断声明。
3. CI `validate-module` 必须通过；失败项会以 GitHub annotation 标在具体文件。
4. 评审只做红线检查（恶意、违法、许可证冲突），不做功能审核；上架依据自动扫描。
5. 合并后维护者将 `.ehmod` 上传到 GitHub Releases，运行索引构建与离线签名。
6. 撤回：作者自行发布新版本或在索引条目标记 `yanked`；项目不维护全局撤回列表。

## 5. 发布物

- `.ehmod` 文件名：`<module-id>-<version>.ehmod`。
- 上传到 GitHub Releases，附 SHA-256；索引中的 `sha256` 必须与实际文件一致。
- 签名可选；`signature.json` / 作者公钥放在模块目录或作者主页。应用会先校验索引签名，再校验包哈希与包签名（若有）。

## 6. 常见拒绝原因

| 原因 | 处理 |
| --- | --- |
| ID 与 GitHub 身份不一致 | 改为 `io.github.<你的用户名>.<名称>` |
| AGPL / 无许可证 / LicenseRef | 更换许可证或改为社区专有源（不进官方索引） |
| 缺少 LICENSE 或 Apache-2.0 缺 NOTICE | 补齐后再提交 |
| 依赖里出现 URL / `-e` / 本地路径 | 改为 PyPI 包名 + 版本范围 |
| 包含密钥、`.env`、私钥 | 移除并使用密钥库 |
| 描述含“诊断/治愈” | 改为非诊断表述 |
| `.ehmod` 路径穿越 / 符号链接 / checksum 不符 | 用校验脚本重新打包 |

问题请开 Issue；安全漏洞请勿公开细节，按仓库安全策略私下报告。

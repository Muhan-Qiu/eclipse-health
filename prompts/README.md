# 提示词索引 · Stage H（模块市场）

> 指挥官文件。Stage G 已验收（30 模块 + 布局 + venv）。当前批次：Stage H，3 个 Agent 并行，low。
> 用户确认：应用内市场先跑通、官方/社区分开、GitHub PR+Actions、离线签名。

## 本轮

| 编号 | 任务 | 提示词 | 报告 |
|---|---|---|---|
| H8 | 市场后端（签名索引/下载/安装/更新） | `130-marketplace-backend.md` | `reports/H8-marketplace-report.md` |
| H9 | 应用内市场 UI（三 tab） | `131-marketplace-ui.md` | `reports/H9-marketplace-ui-report.md` |
| H10 | 静态站 + 开发者 PR/Actions + 文档 | `132-marketplace-site.md` | `reports/H10-marketplace-site-report.md` |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/130-marketplace-backend.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/H8-marketplace-report.md。
```

H9/H10 同理替换。

## 所有权

- H8：`backend/.../marketplace/**`、api 挂载、`tests/marketplace/**`、`scripts/*marketplace*`、`marketplace/{official,community}/index.json`、`docs/MARKETPLACE.md`、`.gitignore`。
- H9：`src/features/modules/marketplace/**`、modules 页/工作区/安装对话框/i18n。
- H10：`marketplace/site/**`、`marketplace/CONTRIBUTING.md`、`.github/**`、`docs/MARKETPLACE_GUIDE.md`。
- H8/H10 都碰 `marketplace/`：H8 只写 official/community/index.json 与 README，H10 只写 site/CONTRIBUTING。

## 边界

- 官方索引只收 OSI 开源；社区标注未审核。
- Ed25519 签名；私钥 `.secrets/`，不提交；dev key 可替换。
- `.ehmod` 走 GitHub Releases；静态站不存任意二进制。
- 不做自动更新/账号系统；安装前展示权限与依赖。

## 收尾

报告齐后：指挥官跑测试/build、生成并签名索引、重打安装包、更新 release notes/校验和。

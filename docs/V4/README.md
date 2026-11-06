# eclipse health V4 开发记录

V4 的目标：修复 V3 中「实验性功能在他人电脑上失效」的问题，重点是**模块导入/加载对宿主机 Python 环境与第三方库的强依赖**。

## 目录

| 文件 | 用途 |
|---|---|
| `BUGS.md` | 问题清单、根因、状态、验收方式 |
| `CHANGELOG.md` | 面向发布的更新日志（用户可读） |
| `ENVIRONMENT.md` | 开发/构建环境与备份约定 |

## 工作约定

1. 每次修复必须先复现、再改、再验证，结果写进 `BUGS.md`。
2. 用户可见的行为变化写进 `CHANGELOG.md`。
3. 每个可交付节点提交并推送到 GitHub `v4` 分支，作为可回滚备份。
4. 大改动前在 `BUGS.md` 记录回滚点（commit hash）。

## 版本基线

- 基线提交：`84b77fd`（V3 `feat/ui-alignment` 分支）
- V4 分支：`v4`（从基线拉出）
- 远程：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`

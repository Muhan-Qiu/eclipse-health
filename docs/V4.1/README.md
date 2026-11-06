# eclipse health V4.1 开发记录

V4.1 是 V4 的修复版本，延续 V4 的约定：每条问题先复现、再修复、再验证，结果写进 `BUGS.md`。

## 本版修复

| 编号 | 问题 | 状态 |
|---|---|---|
| BUG-101 | 助手回复中的 Markdown 未渲染，星号/井号/列表按纯文本显示 | `FIXED` |
| BUG-102 | 助手防御性过高：过度免责、急于撇清关系、缺少可执行建议 | `FIXED` |

## 目录

| 文件 | 用途 |
|---|---|
| `BUGS.md` | 问题清单、根因、修复、验收方式 |
| `CHANGELOG.md` | 面向发布的更新日志（用户可读） |
| `ENVIRONMENT.md` | 开发/构建环境与备份约定 |

## 版本基线

- 基线提交：`42377bc`（V4 `v4` 分支）
- V4.1 分支：`v4.1`
- 远程：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`

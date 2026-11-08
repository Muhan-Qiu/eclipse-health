# eclipse health V4.2 开发记录

V4.2 是 V4.1 的修复版本。本版只修一个问题：**除 Cardia 外，其他分析引擎（relay-ecg）无法正常分析心电图**，表现为输入维度不匹配或分析过程直接报错。

延续 V4 / V4.1 的约定：每条问题先复现、再修复、再验证，结果写进 `BUGS.md`，修复提交与安装包哈希一并记录，方便回溯。

## 本版修复

| 编号 | 问题 | 状态 |
|---|---|---|
| BUG-201 | 非 Cardia 分析引擎（relay-ecg 的 7 个模型）在 ECG 记录上全部失败：`仅支持 2/3 维输入，模型输入维度为 4` / `ValueError: cannot reshape array of size 37908 into shape (162,2,234)` | `FIXED` |
| BUG-202 | relay 引擎只显示分类概率，缺少心率、HRV、信号质量、异常心搏占比 | `FIXED` |
| BUG-203 | Cardia 分析里 `lead_out_of_distribution` 警告显示乱码 | `FIXED` |
| BUG-204 | relay 引擎在手表单导联记录上 SVEB 比例异常高，界面缺少醒目提示 | `FIXED` |

## 目录

| 文件 | 用途 |
|---|---|
| `BUGS.md` | 问题清单、根因、修复、验收方式 |
| `CHANGELOG.md` | 面向发布的更新日志（用户可读） |
| `ENVIRONMENT.md` | 开发/构建环境、验证命令、安装包记录与备份约定 |

## 版本基线

- 基线提交：`63b44d9`（V4.1 分支 `v4.1`）
- V4.2 分支：`v4.2`
- 远程：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`
- 应用 / Tauri / 后端版本：`0.1.2`

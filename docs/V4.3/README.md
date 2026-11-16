# eclipse health V4.3 开发记录

V4.3 是模块体验改版：**每个模块都有自己的工作台**，侧栏可直接打开模块，助手对话可以「+」选择本轮优先模块。工程仍在 V4.2 源码上继续（git 分支 `v4.3`），没有复制整份工程。

## 本版内容

| 编号 | 内容 | 状态 |
|---|---|---|
| M-301 | 每个已安装模块都有独立工作台 `/modules/:moduleId`（状态、页面、仪表盘卡片、工具试运行、模型卡、记录类型、权限、审计） | `DONE` |
| M-302 | 侧栏直接列出已安装模块，点击进入工作台；模块中心列表增加「打开」按钮，详情面板增加「打开工作台」 | `DONE` |
| M-303 | 助手输入区「+」选择本轮优先模块；`moduleIds` 随会话保存，消息与透明面板回显 | `DONE` |
| M-304 | 后端优先模块工具排序 + 系统提示词模块清单；其他已启用模块工具仍可用 | `DONE` |
| M-305 | Node 编码/模块/`.ehmod` 校验脚本，提前发现 BOM、U+FFFD、坏 JSON、校验和不一致 | `DONE` |

## 目录

| 文件 | 用途 |
|---|---|
| `MODULE_WORKBENCH.md` | 模块工作台、Agent 模块选择契约、校验脚本与编码规范 |
| `CHANGELOG.md` | 面向发布的更新日志 |
| `../V4.2/` | V4.2 的修复记录（历史） |

## 版本基线

- 基线分支：`v4.2`（V4.2 最后提交 `b42ce89`）
- V4.3 分支：`v4.3`
- 应用 / Tauri / 后端版本：`0.1.3`

## 验证命令

```powershell
npm run build
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm run check:modules
npm run check:packages
```

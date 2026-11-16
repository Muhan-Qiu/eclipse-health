# eclipse health V4.5 开发记录

V4.5 是 `0.2.0` 版本：以修复隐藏 bug、补完未完全实现的功能、重做第 4–8 套主题与模块工作台为主。
工程从 V4.3 工作树建立（基线提交 `209ad4f`），V4.3 原目录保留不动，作为可回滚副本。

## 本版范围

| 编号 | 内容 | 状态 |
|---|---|---|
| V45-01 | 健康评分 `missing` 契约修复 + 分类 id 归一化 + 缺失分类占位瓦片 | `DONE` |
| V45-02 | 评分/建议 `lang=zh|en` 本地化与测试 | `DONE` |
| V45-03 | Windows 大模块包安装失败（目录 rename → 逐文件搬移） | `DONE` |
| V45-04 | 8 套主题重做（完整令牌、空间氛围、玻璃、对比度） | `DONE` |
| V45-05 | 侧栏 / 顶栏 / PageHeader / 仪表盘布局统一 | `DONE` |
| V45-06 | 模块中心与工作台重排、Cardia/Relay 中英文文案 | `DONE` |
| V45-07 | 记录详情节律条、标注防重叠、分析面板、心搏列表 | `DONE` |
| V45-08 | 导入警告 23 个中英文案、Vite 字体 403 | `DONE` |
| V45-09 | 版本号 0.2.0、模块包与市场索引重建、安装包 | `DONE` |

## 目录

| 文件 | 用途 |
|---|---|
| `CHANGELOG.md` | 面向用户的更新日志 |
| `BUGS.md` | 本版修复的根因、修复点、验证方式 |
| `MODULES.md` | 模块工作台与模块文案结构 |
| `../V4.3/` | 上一版记录（历史） |

## 验证

- 前端：`npx tsc --noEmit`、`npm run build` 通过；Playwright 全路由 1024/1280/1440 无横向溢出、无控制台错误。
- 后端：`pytest backend/tests -q -m "not slow"` 通过（含新增评分 i18n、模块搬移测试）；`ruff check backend` 通过。
- 模块：`npm run check:modules`（34 manifests / 771 files，0 错误）、`npm run check:packages`（32 包，0 错误）。
- 端到端：安装 relay-ecg → 用 relay-k2 分析 30 分钟 MIT-BIH 记录 → `completed`；Apple ECG CSV 预览/提交；报告 PDF 生成/下载；Mock 助手对话。

## 构建

```powershell
# 前端
npm run build

# 模块包 + 签名索引（需要 .secrets/marketplace_ed25519.key）
backend\.venv\Scripts\python.exe scripts\pack_official_modules.py
backend\.venv\Scripts\python.exe scripts\build_marketplace_index.py

# 安装包（PyInstaller sidecar + Tauri NSIS）
powershell -File scripts\build_release.ps1
```

安装包产物在 `src-tauri\target\release\bundle\nsis\`。

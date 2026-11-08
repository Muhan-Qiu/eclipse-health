# 环境与备份约定（V4.2）

## 本机开发环境（2026-11-07 核对）

| 项 | 值 |
|---|---|
| OS | Windows 11 Home China 10.0.22631 |
| Python（后端 venv） | 3.12.7（`backend/.venv`） |
| Node.js | v24.13.0 |
| 前端依赖 | `npm install`（无新增依赖） |
| 后端依赖 | 无新增依赖；使用核心已有的 `wfdb` 做 R 峰检测 |

## 常用验证

```powershell
# 前端
npx tsc --noEmit
npm run build

# 后端
cd backend
.venv\Scripts\python.exe -m pytest tests/analysis_service -q
.venv\Scripts\python.exe -m ruff check src tests/analysis_service/test_relay_onnx_engine.py
```

## 真实 relay 模型验证

用本机已安装的 relay-ecg 权重和 `%LOCALAPPDATA%\eclipse-health\signals\` 下的真实记录逐个跑：

```powershell
cd backend
MPLBACKEND=Agg .venv\Scripts\python.exe scripts\verify_relay_engines.py `
  --signal "$env:LOCALAPPDATA\eclipse-health\signals\sig_01a19bc6-a9a7-79c8-87ba-a7804c92b30f.f32" `
  --fs 500
```

预期：7 个模型全部输出 `OK`，并打印每个模型的评分心搏数、尾部丢弃数和分类概率摘要。

## 本机构建产物（2026-11-07）

| 项 | 值 |
|---|---|
| 安装包 | `src-tauri/target/release/bundle/nsis/eclipse health_0.1.2_x64-setup.exe` |
| 大小 | 320.67 MiB（336,242,592 bytes） |
| SHA-256 | `8c9d666207b40fd6552274ca9c6856082babda8053e470f5bceb8c684c03f845` |
| 版本 | 应用 / Tauri / 后端均为 `0.1.2` |
| 冒烟 | 构建产物 sidecar 与静默安装后的 sidecar 均返回 `status=ok`、`version=0.1.2`；API 发起 relay-k2 / resnet1d / relay-k8 / relay-k12 分析均 `completed`；relay-k2 结果包含心率、RR、SDNN、RMSSD、pNN50、N/SVEB/VEB/F 比例与质量分 |

构建注意：`scripts/build_release.ps1` 现在用 `python -m PyInstaller` 而不是
`Scripts\pyinstaller.exe`。复制/共享 venv 时入口 exe 的路径可能仍指向旧目录，
用 `python -m` 能保证当前 venv 与源码生效。

> 构建前确认 `backend/packaging/wheelhouse` 与 `dist/modules` 存在；本机已从 V4.1 复用。
> relay-ecg / relay-sleep 的 ONNX 权重不随 git 提交，安装包内不包含；本机验证使用
> `%LOCALAPPDATA%\eclipse-health\modules\` 下已安装的权重。

## 备份与回滚

- 远程仓库：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`
- V4.2 分支：`v4.2`；V4.1 基线分支：`v4.1`（commit `63b44d9`）
- 提交推送节奏：
  - 修复完成并验证：提交 + 推送
  - 安装包/大改动前：额外打 tag（`v4.2-baseline`、`v4.2-m1` …）

## 回滚方法

```bash
git fetch origin
git checkout v4.2
git reset --hard <上一个可用 commit>   # 或 git revert <commit>
git push --force-with-lease origin v4.2  # 仅在确认需要回滚共享分支时
```

## 本机备注：行尾符与模块校验和

V4.2 工作树使用 `core.autocrlf=false`。仓库内 `modules/official/*/checksums.json`
按 LF 计算；如果 Windows 全局 `core.autocrlf=true` 把文本文件检出成 CRLF，
`verify_checksums()` 会误报校验失败（V4.1 工作树也会）。克隆后如遇该问题：

```powershell
git config core.autocrlf false
git checkout-index -a -f
```

或只对被改坏的模块文本文件重新检出（注意：这会覆盖未提交修改）。

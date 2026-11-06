# 环境与备份约定（V4）

## 本机开发环境（2026-11-06 核对）

| 项 | 值 |
|---|---|
| OS | Windows 11 Home China 10.0.22631 |
| Python（PATH） | 3.12.7 |
| 其他 Python | 3.9（`py -3.9`）、Anaconda 3.12 |
| Node.js | v24.13.0 |
| 后端 venv | 克隆后不存在，需要重新创建 |

## 后端环境创建

```powershell
cd backend
uv sync          # 或 python -m venv .venv && .venv\Scripts\pip install -e .
```

> 注意：V4 要解决的核心问题之一就是「不能要求用户/开发者本机 Python 环境正好匹配」。
> 这里的开发环境要求会随修复推进逐步降低，最终目标是**干净 Windows + 安装包即可运行**。

## 备份与回滚

- 远程仓库：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`
- V4 分支：`v4`；V3 基线分支：`feat/ui-alignment`
- 提交推送节奏：
  - V4 初始化：已推送基线
  - 每个 bug 修复完成并验证：提交 + 推送
  - 安装包/大改动前：额外打 tag（`v4-baseline`、`v4-m1` …）

## 回滚方法

```bash
git fetch origin
git checkout v4
git reset --hard <上一个可用 commit>   # 或 git revert <commit>
git push --force-with-lease origin v4  # 仅在确认需要回滚共享分支时
```

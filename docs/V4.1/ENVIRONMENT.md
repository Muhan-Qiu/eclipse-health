# 环境与备份约定（V4.1）

## 本机开发环境（2026-11-06 核对）

| 项 | 值 |
|---|---|
| OS | Windows 11 Home China 10.0.22631 |
| Python（PATH） | 3.12 |
| Node.js | v24.13.0 |
| 后端 venv | `backend/.venv`（克隆后重新创建） |
| 前端依赖 | `npm install`（新增 `react-markdown`、`remark-gfm`） |

## 后端环境创建

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e . pytest ruff
```

## 常用验证

```powershell
# 前端
npx tsc --noEmit
npm run build

# 后端
cd backend
.venv\Scripts\python.exe -m pytest tests/assistant tests/coach -q
.venv\Scripts\python.exe -m ruff check src tests
```

## 备份与回滚

- 远程仓库：`ssh://git@ssh.github.com:443/Muhan-Qiu/eclipse-health.git`
- V4.1 分支：`v4.1`；V4 基线分支：`v4`（commit `42377bc`）
- 提交推送节奏：
  - 每个 bug 修复完成并验证：提交 + 推送
  - 安装包/大改动前：额外打 tag（`v4.1-baseline`、`v4.1-m1` …）

## 回滚方法

```bash
git fetch origin
git checkout v4.1
git reset --hard <上一个可用 commit>   # 或 git revert <commit>
git push --force-with-lease origin v4.1  # 仅在确认需要回滚共享分支时
```

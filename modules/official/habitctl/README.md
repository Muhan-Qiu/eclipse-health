# habitctl · 习惯追踪

适配自 [blinry/habitctl](https://github.com/blinry/habitctl)（Rust，GPL-2.0-or-later）。
本模块是**薄适配层**：不复制上游源码，通过子进程调用 `habitctl` 并解析文本输出。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `habits.list` | 返回 `{habits, summary}`；可传 `params.text` 离线解析 |
| `habits.summary` | 返回 `{count, doneToday, bestStreak, totalStreak}` |
| `habits.form` | 表单默认值 |
| `habits.log` | 校验并写入一次打卡 |

文本格式：每行可带 `[x]` / `[ ]`、`✔` / `✗`，名称后可跟 `streak=12`。

## 权限与依赖

- 权限：`records:read`、`records:write`
- pip 依赖：无；上游为 Rust 二进制，通过 `HABITCTL_BINARY`（默认 `habitctl`）指定。

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_habitctl.py -q
```

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。

# Echo Demo

模块内核（B1）自检用的最小 `.ehmod` 模块。运行在独立 Python 子进程中，通过 stdio
按行 JSON-RPC 2.0 与核心通信，不依赖 `eclipse_health_backend`。

## 方法

| 方法 | 参数 | 说明 |
|---|---|---|
| `initialize` | `apiVersion`, `permissions`, `locale`, `config` | 握手，返回能力与注入的权限 |
| `hello` | `name?` | 问候 |
| `echo` | `text` | 原样返回文本与长度 |
| `fail` | `mode`: `error` / `crash` / `timeout` | 测试错误、崩溃恢复、调用超时 |
| `call_core` | `method`, `params` | 向核心发起受限 RPC（测试权限拒绝） |
| `health` | — | 存活检查 |
| `deactivate` | — | 回复后退出 |

## 打包

```powershell
backend\.venv\Scripts\python.exe scripts\pack_demo.py
```

输出 `dist/demo.echo-1.0.0.ehmod`，并打印 SHA-256。

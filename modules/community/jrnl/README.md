# jrnl · 日记与心情

适配自 [jrnl-org/jrnl](https://github.com/jrnl-org/jrnl)（Python，GPL-3.0）。
本模块是**薄适配层**：不复制上游源码，通过子进程调用 `jrnl --export json`
并解析导出条目；也接受调用方直接传入 `params.text`。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `journal.list` | 返回条目与汇总，支持 `limit` |
| `journal.get` | 按 `title` 精确取一条 |
| `journal.summary` | 总条数、最新日期、标签计数 |
| `journal.search` | 关键词 + 标签搜索，供 LLM 工具调用 |

LLM 工具：`journal.search`（需授予 `llm` 权限）。

## 权限与依赖

- 权限：`records:read`、`llm`
- pip 依赖：`jrnl>=4.0,<5`（装进模块独立 venv）
- 环境变量 `JRNL_BINARY` 可覆盖可执行文件名。

## 隐私

日记正文只在本机内存与返回结果中处理；不写日志、不上传。上游加密与密钥环行为保持不变。

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_jrnl.py -q
```

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。

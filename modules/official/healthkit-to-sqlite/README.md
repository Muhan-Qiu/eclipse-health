# healthkit-to-sqlite · Apple Health 导入

适配自 [dogsheep/healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite)（Apache-2.0）。
本模块只复用**解析思路**，用 stdlib `zipfile` + `xml.etree.ElementTree.iterparse`
重写，不依赖 sqlite-utils，也不写数据库。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `import.healthkit` | 解析 `export.zip` 或 `export.xml`，返回记录与计数 |
| `import.summary` | 最近一次导入的汇总（供页面/面板） |

- `params.path`：用户选择的 zip/xml；
- `params.limit`：最多解析 1..200000 条，默认 100000；
- 返回最多 2000 条记录；更大结果写临时文件并返回 `resultRef`。

## 贡献点

- `sources`：`apple-health`
- `importFormats`：`apple-health-export`（`.zip` / `.xml`）
- `recordTypes`：`vital.measurement`、`activity.sample`、`sleep.session`、`activity.workout`

## 隐私

丢弃 `sourceName`、`device` 等设备标识；不保留文件路径；不写日志。数据只在本机处理。

## 权限与依赖

- 权限：`files:user-selected`、`records:write`
- pip 依赖：无（纯 stdlib）

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_healthkit-to-sqlite.py -q
```

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。
